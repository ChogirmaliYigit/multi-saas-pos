"""Branches, shop settings, and tax rates.

The parts of a shop's configuration an owner edits rarely and expects to stay
put.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, update

from app.api.deps import CurrentTenant, DbSession, require
from app.core import quotas
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Permission
from app.models.catalog import Product, TaxRate
from app.models.enums import OrderStatus
from app.models.sales import Order
from app.models.tenant import Branch
from app.models.user import User
from app.schemas.common import Message
from app.schemas.shop import (
    BranchIn,
    BranchOut,
    BranchUpdate,
    ShopSettings,
    ShopSettingsUpdate,
    TaxRateUpdate,
)

router = APIRouter(tags=["shop"])


# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------


@router.get(
    "/branches",
    response_model=list[BranchOut],
    dependencies=[Depends(require(Permission.BRANCH_READ))],
)
async def list_branches(db: DbSession) -> list[BranchOut]:
    branches = list(
        await db.scalars(
            select(Branch)
            .where(Branch.deleted_at.is_(None))
            .order_by(Branch.is_default.desc(), Branch.name)
        )
    )
    if not branches:
        return []

    ids = [b.id for b in branches]
    staff = dict(
        (
            await db.execute(
                select(User.branch_id, func.count(User.id))
                .where(User.branch_id.in_(ids), User.deleted_at.is_(None))
                .group_by(User.branch_id)
            )
        ).all()
    )
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    orders = dict(
        (
            await db.execute(
                select(Order.branch_id, func.count(Order.id))
                .where(
                    Order.branch_id.in_(ids),
                    Order.status != OrderStatus.DRAFT,
                    Order.completed_at >= thirty_days_ago,
                )
                .group_by(Order.branch_id)
            )
        ).all()
    )
    # Products are shop-wide, not per branch; the count is shown so an empty
    # new branch does not look broken.
    product_count = (
        await db.scalar(select(func.count(Product.id)).where(Product.deleted_at.is_(None)))
    ) or 0

    return [
        BranchOut(
            **{
                field: getattr(branch, field)
                for field in BranchOut.model_fields
                if hasattr(branch, field)
            },
            staff_count=staff.get(branch.id, 0),
            product_count=product_count,
            orders_last_30_days=orders.get(branch.id, 0),
        )
        for branch in branches
    ]


@router.post(
    "/branches",
    response_model=BranchOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Permission.BRANCH_MANAGE))],
)
async def create_branch(payload: BranchIn, db: DbSession, tenant: CurrentTenant) -> BranchOut:
    await quotas.assert_can_add_branch(db, tenant.id)

    if await db.scalar(
        select(Branch.id).where(Branch.code == payload.code, Branch.deleted_at.is_(None))
    ):
        raise ConflictError(f"Branch code {payload.code} is already in use.", code="code_taken")

    if payload.is_default:
        await db.execute(update(Branch).values(is_default=False))

    branch = Branch(**payload.model_dump(), is_active=True)
    db.add(branch)
    await db.flush()
    return BranchOut(
        **{f: getattr(branch, f) for f in BranchOut.model_fields if hasattr(branch, f)}
    )


@router.patch(
    "/branches/{branch_id}",
    response_model=BranchOut,
    dependencies=[Depends(require(Permission.BRANCH_MANAGE))],
)
async def update_branch(branch_id: uuid.UUID, payload: BranchUpdate, db: DbSession) -> BranchOut:
    branch = await db.scalar(
        select(Branch).where(Branch.id == branch_id, Branch.deleted_at.is_(None))
    )
    if branch is None:
        raise NotFoundError("Branch not found.")

    updates = payload.model_dump(exclude_unset=True)

    if updates.get("is_active") is False and branch.is_default:
        raise ConflictError(
            "Make another branch the default before deactivating this one.",
            code="default_branch",
        )

    if updates.get("is_default"):
        # Exactly one default, or new staff and stock land somewhere arbitrary.
        await db.execute(update(Branch).values(is_default=False))

    for field, value in updates.items():
        setattr(branch, field, value)

    await db.flush()
    return BranchOut(
        **{f: getattr(branch, f) for f in BranchOut.model_fields if hasattr(branch, f)}
    )


@router.delete(
    "/branches/{branch_id}",
    response_model=Message,
    dependencies=[Depends(require(Permission.BRANCH_MANAGE))],
)
async def delete_branch(branch_id: uuid.UUID, db: DbSession) -> Message:
    branch = await db.scalar(
        select(Branch).where(Branch.id == branch_id, Branch.deleted_at.is_(None))
    )
    if branch is None:
        raise NotFoundError("Branch not found.")

    remaining = (
        await db.scalar(
            select(func.count(Branch.id)).where(Branch.deleted_at.is_(None), Branch.id != branch_id)
        )
    ) or 0
    if remaining == 0:
        raise ConflictError("A shop needs at least one branch.", code="last_branch")
    if branch.is_default:
        raise ConflictError("Make another branch the default first.", code="default_branch")

    sold = (await db.scalar(select(func.count(Order.id)).where(Order.branch_id == branch_id))) or 0

    # Soft delete regardless: orders reference the branch, and a receipt
    # reprinted next year still has to name where it was rung up.
    branch.deleted_at = func.now()
    branch.is_active = False
    await db.execute(update(User).where(User.branch_id == branch_id).values(branch_id=None))

    return Message(
        message=(
            f"Branch closed. Its {sold} past sales are retained." if sold else "Branch closed."
        )
    )


# ---------------------------------------------------------------------------
# Shop settings
# ---------------------------------------------------------------------------


@router.get(
    "/shop",
    response_model=ShopSettings,
    dependencies=[Depends(require(Permission.TENANT_READ))],
)
async def get_shop(tenant: CurrentTenant) -> ShopSettings:
    return ShopSettings.model_validate(tenant)


@router.patch(
    "/shop",
    response_model=ShopSettings,
    dependencies=[Depends(require(Permission.TENANT_UPDATE))],
)
async def update_shop(
    payload: ShopSettingsUpdate, db: DbSession, tenant: CurrentTenant
) -> ShopSettings:
    updates = payload.model_dump(exclude_unset=True)

    # Merge rather than replace: a client sending one switch should not wipe
    # the rest of the shop's configuration.
    if "settings" in updates and updates["settings"] is not None:
        updates["settings"] = {**(tenant.settings or {}), **updates["settings"]}

    for field, value in updates.items():
        setattr(tenant, field, value)

    await db.flush()
    return ShopSettings.model_validate(tenant)


# ---------------------------------------------------------------------------
# Tax rates
# ---------------------------------------------------------------------------


@router.patch(
    "/catalog/tax-rates/{rate_id}",
    response_model=dict,
    dependencies=[Depends(require(Permission.PRODUCT_MANAGE))],
)
async def update_tax_rate(rate_id: uuid.UUID, payload: TaxRateUpdate, db: DbSession) -> dict:
    """Edit a rate.

    Changing a rate does NOT alter past sales: every order line stored the
    rate and the tax amount at the time, precisely so a tax return for last
    quarter is not rewritten by a change made today.
    """
    rate = await db.scalar(
        select(TaxRate).where(TaxRate.id == rate_id, TaxRate.deleted_at.is_(None))
    )
    if rate is None:
        raise NotFoundError("Tax rate not found.")

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_default"):
        await db.execute(update(TaxRate).values(is_default=False))

    for field, value in updates.items():
        setattr(rate, field, value)

    await db.flush()
    return {
        "id": str(rate.id),
        "name": rate.name,
        "rate": str(rate.rate),
        "is_inclusive": rate.is_inclusive,
        "is_default": rate.is_default,
        "is_active": rate.is_active,
    }


@router.delete(
    "/catalog/tax-rates/{rate_id}",
    response_model=Message,
    dependencies=[Depends(require(Permission.PRODUCT_MANAGE))],
)
async def delete_tax_rate(rate_id: uuid.UUID, db: DbSession) -> Message:
    rate = await db.scalar(
        select(TaxRate).where(TaxRate.id == rate_id, TaxRate.deleted_at.is_(None))
    )
    if rate is None:
        raise NotFoundError("Tax rate not found.")

    in_use = (
        await db.scalar(
            select(func.count(Product.id)).where(
                Product.tax_rate_id == rate_id, Product.deleted_at.is_(None)
            )
        )
    ) or 0
    if in_use:
        raise ConflictError(
            f"{in_use} product{'s' if in_use != 1 else ''} still use this rate.",
            code="rate_in_use",
            details={"products": in_use},
        )

    rate.deleted_at = func.now()
    rate.is_active = False
    return Message(message="Tax rate removed.")
