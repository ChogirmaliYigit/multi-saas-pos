from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentTenant, CurrentUser, DbSession, require
from app.core import quotas
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.permissions import Permission, permissions_for
from app.core.security import hash_password, hash_pin
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.employees import (
    EmployeeIn,
    EmployeeOut,
    EmployeeUpdate,
    ResetPasswordIn,
)
from app.services import auth_service

router = APIRouter(prefix="/employees", tags=["employees"])


def _to_out(user: User) -> EmployeeOut:
    return EmployeeOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        branch_id=user.branch_id,
        phone=user.phone,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        has_pin=user.pin_hash is not None,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        permissions=sorted(permissions_for(user.role, user.permission_overrides)),
    )


def _assert_can_target(actor: User, target: User) -> None:
    """A manager may not edit an owner, and nobody may edit themselves into a
    different role -- the two ways an RBAC system usually gets escalated."""
    if actor.id == target.id:
        raise PermissionDeniedError(
            "Change your own details from your account page.",
            code="self_edit_blocked",
        )
    if target.role is UserRole.OWNER and actor.role is not UserRole.OWNER:
        raise PermissionDeniedError("Only an owner can manage another owner.")


@router.get(
    "",
    response_model=Page[EmployeeOut],
    dependencies=[Depends(require(Permission.USER_READ))],
)
async def list_employees(
    db: DbSession,
    search: str | None = Query(default=None, max_length=100),
    role: UserRole | None = None,
    include_inactive: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> Page[EmployeeOut]:
    conditions = [User.deleted_at.is_(None)]
    if not include_inactive:
        conditions.append(User.is_active.is_(True))
    if role:
        conditions.append(User.role == role)
    if search:
        term = f"%{search.lower()}%"
        conditions.append(func.lower(User.full_name).like(term) | func.lower(User.email).like(term))

    total = await db.scalar(select(func.count()).select_from(User).where(*conditions))
    rows = await db.scalars(
        select(User)
        .where(*conditions)
        .order_by(User.full_name)
        .offset((page - 1) * size)
        .limit(size)
    )
    return Page[EmployeeOut](
        items=[_to_out(row) for row in rows], total=total or 0, page=page, size=size
    )


@router.post(
    "",
    response_model=EmployeeOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Permission.USER_CREATE))],
)
async def create_employee(
    payload: EmployeeIn, db: DbSession, actor: CurrentUser, tenant: CurrentTenant
) -> EmployeeOut:
    await quotas.assert_can_add_user(db, tenant.id)

    # A manager can hire cashiers, not owners. Without this, USER_CREATE is a
    # privilege-escalation button.
    if payload.role is UserRole.OWNER and actor.role is not UserRole.OWNER:
        raise PermissionDeniedError("Only an owner can create another owner.")

    existing = await db.scalar(
        select(User.id).where(
            func.lower(User.email) == payload.email.lower(),
            User.tenant_id == tenant.id,
            User.deleted_at.is_(None),
        )
    )
    if existing:
        raise ConflictError("Someone already uses that email at this shop.", code="email_taken")

    user = User(
        tenant_id=tenant.id,
        branch_id=payload.branch_id or actor.branch_id,
        email=payload.email.lower(),
        full_name=payload.full_name,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        pin_hash=hash_pin(payload.pin) if payload.pin else None,
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return _to_out(user)


@router.get(
    "/{user_id}",
    response_model=EmployeeOut,
    dependencies=[Depends(require(Permission.USER_READ))],
)
async def get_employee(user_id: uuid.UUID, db: DbSession) -> EmployeeOut:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise NotFoundError("Employee not found.")
    return _to_out(user)


@router.patch(
    "/{user_id}",
    response_model=EmployeeOut,
    dependencies=[Depends(require(Permission.USER_UPDATE))],
)
async def update_employee(
    user_id: uuid.UUID, payload: EmployeeUpdate, db: DbSession, actor: CurrentUser
) -> EmployeeOut:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise NotFoundError("Employee not found.")
    _assert_can_target(actor, user)

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("role") is UserRole.OWNER and actor.role is not UserRole.OWNER:
        raise PermissionDeniedError("Only an owner can promote someone to owner.")

    for field, value in updates.items():
        setattr(user, field, value)

    # A deactivated employee must lose their live sessions immediately, not
    # whenever their access token happens to expire.
    if updates.get("is_active") is False:
        await auth_service._revoke_all_for_user(db, user.id)

    await db.flush()
    return _to_out(user)


@router.post(
    "/{user_id}/reset-password",
    response_model=Message,
    dependencies=[Depends(require(Permission.USER_UPDATE))],
)
async def reset_password(
    user_id: uuid.UUID, payload: ResetPasswordIn, db: DbSession, actor: CurrentUser
) -> Message:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise NotFoundError("Employee not found.")
    _assert_can_target(actor, user)

    user.hashed_password = hash_password(payload.new_password)
    await auth_service._revoke_all_for_user(db, user.id)
    return Message(message="Password reset. Their other sessions were signed out.")


@router.delete(
    "/{user_id}",
    response_model=Message,
    dependencies=[Depends(require(Permission.USER_DELETE))],
)
async def delete_employee(user_id: uuid.UUID, db: DbSession, actor: CurrentUser) -> Message:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise NotFoundError("Employee not found.")
    _assert_can_target(actor, user)

    # Soft delete: their name is on every order they rang up.
    user.deleted_at = func.now()
    user.is_active = False
    await auth_service._revoke_all_for_user(db, user.id)
    return Message(message="Employee removed.")
