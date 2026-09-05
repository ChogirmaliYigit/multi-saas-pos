from __future__ import annotations

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import InvalidCredentialsError, PermissionDeniedError
from app.core.permissions import permissions_for
from app.core.security import hash_password, hash_pin, verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    PinLoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SessionInfo,
    SetPinRequest,
    SignupRequest,
    TerminalStaff,
    TokenPair,
    UserPublic,
)
from app.schemas.common import Message
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ua = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    # Behind Nginx the real client is in X-Forwarded-For; trust it only
    # because the proxy config in deployment/ overwrites it, never appends.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    return ua, ip


@router.post("/signup", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: DbSession) -> User:
    """Self-serve shop registration. Public."""
    _tenant, owner = await auth_service.signup(db, payload)
    return owner


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenPair:
    """Password login.

    The shop is taken from the subdomain when present; `tenant_slug` in the
    body is the fallback for clients that do not use subdomains. With neither,
    only platform staff can authenticate.
    """
    slug = getattr(request.state, "tenant_slug", None) or payload.tenant_slug
    user = await auth_service.authenticate(
        db, email=payload.email, password=payload.password, tenant_slug=slug
    )
    ua, ip = _client_meta(request)
    return await auth_service.issue_token_pair(db, user, user_agent=ua, ip_address=ip)


@router.post("/pin-login", response_model=TokenPair)
async def pin_login(
    payload: PinLoginRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> TokenPair:
    """Swap cashiers on a terminal without retyping a password.

    Requires an existing valid session on the device: the terminal is
    authenticated once by a manager, after which staff switch by PIN. A PIN
    alone is four digits -- far too weak to be a standalone credential exposed
    to the internet.
    """
    if current_user.tenant_id is None:
        raise PermissionDeniedError("PIN login is only available inside a shop.")

    user = await auth_service.authenticate_pin(
        db, tenant_id=current_user.tenant_id, user_id=payload.user_id, pin=payload.pin
    )
    ua, ip = _client_meta(request)
    return await auth_service.issue_token_pair(db, user, user_agent=ua, ip_address=ip)


@router.get("/terminal/staff", response_model=list[TerminalStaff])
async def terminal_staff(db: DbSession, current_user: CurrentUser) -> list[TerminalStaff]:
    """Avatar picker for the PIN screen. Returns names only -- no e-mail
    addresses, so a shop-floor tablet never displays login identifiers."""
    if current_user.tenant_id is None:
        raise PermissionDeniedError()

    users = await db.scalars(
        select(User)
        .where(
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            User.role.in_([UserRole.CASHIER, UserRole.MANAGER, UserRole.OWNER]),
        )
        .order_by(User.full_name)
    )
    return [
        TerminalStaff(
            id=u.id,
            full_name=u.full_name,
            role=u.role,
            avatar_url=u.avatar_url,
            has_pin=u.pin_hash is not None,
        )
        for u in users
    ]


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, request: Request, db: DbSession) -> TokenPair:
    """Rotate a refresh token. Public: the token itself is the credential."""
    ua, ip = _client_meta(request)
    return await auth_service.rotate_refresh_token(
        db, presented_token=payload.refresh_token, user_agent=ua, ip_address=ip
    )


@router.post("/logout", response_model=Message)
async def logout(payload: RefreshRequest, db: DbSession) -> Message:
    await auth_service.revoke_refresh_token(db, payload.refresh_token)
    return Message(message="Signed out.")


@router.get("/me", response_model=SessionInfo)
async def me(request: Request, current_user: CurrentUser) -> SessionInfo:
    """Everything the frontend needs to render the shell: identity, shop, and
    the exact permission set, so the UI hides what the API would refuse."""
    return SessionInfo(
        user=UserPublic.model_validate(current_user),
        tenant_slug=getattr(request.state, "tenant_slug", None),
        permissions=sorted(permissions_for(current_user.role, current_user.permission_overrides)),
    )


@router.post("/change-password", response_model=Message)
async def change_password(
    payload: ChangePasswordRequest, db: DbSession, current_user: CurrentUser
) -> Message:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise InvalidCredentialsError("Current password is incorrect.")
    current_user.hashed_password = hash_password(payload.new_password)
    # Every other session is invalidated -- that is the point of changing a
    # password after a suspected compromise.
    await auth_service._revoke_all_for_user(db, current_user.id)
    return Message(message="Password updated. Other sessions were signed out.")


@router.post("/set-pin", response_model=Message)
async def set_pin(payload: SetPinRequest, db: DbSession, current_user: CurrentUser) -> Message:
    current_user.pin_hash = hash_pin(payload.pin)
    return Message(message="Terminal PIN updated.")


@router.post("/forgot-password", response_model=Message)
async def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: DbSession
) -> Message:
    """Send a reset link.

    Always answers the same, whether or not the address belongs to anyone.
    A "no such account" response would turn this form into a directory of who
    works at a shop, and the people most likely to probe it are exactly the
    ones a shop least wants finding out.
    """
    slug = getattr(request.state, "tenant_slug", None) or payload.tenant_slug
    ua, ip = _client_meta(request)

    await auth_service.request_password_reset(
        db,
        email=payload.email,
        tenant_slug=slug,
        ip_address=ip,
        user_agent=ua,
    )
    return Message(message="If that address has an account, a reset link is on its way.")


@router.post("/reset-password", response_model=Message)
async def reset_password(payload: ResetPasswordRequest, db: DbSession) -> Message:
    """Consume a reset link and set a new password.

    Public by necessity: the person using it cannot sign in. The token is the
    credential, it works once, and every other session is revoked on success.
    """
    await auth_service.reset_password(db, token=payload.token, new_password=payload.new_password)
    return Message(message="Password updated. You can sign in now; other sessions were signed out.")
