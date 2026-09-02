"""Plan limit enforcement.

`plans` has carried max_branches / max_users / max_products /
max_orders_per_month since Step 1, but nothing checked them -- a Basic tenant
could create ten thousand products and the only signal would be the bill never
going up. These are checked at the point of creation, which is the only moment
a refusal is actionable for the user.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import QuotaExceededError
from app.db.tenant_filter import SKIP_TENANT_FILTER
from app.models.catalog import Product
from app.models.enums import OrderStatus, SubscriptionStatus
from app.models.sales import Order
from app.models.subscription import Plan, Subscription
from app.models.tenant import Branch
from app.models.user import User

_NO_FILTER = {SKIP_TENANT_FILTER: True}


async def plan_for(session: AsyncSession, tenant_id: uuid.UUID) -> Plan | None:
    return await session.scalar(
        select(Plan)
        .join(Subscription, Subscription.plan_id == Plan.id)
        .where(
            Subscription.tenant_id == tenant_id,
            Subscription.status.notin_([SubscriptionStatus.CANCELED, SubscriptionStatus.EXPIRED]),
        )
        .execution_options(**_NO_FILTER)
    )


async def _count(session: AsyncSession, model, tenant_id: uuid.UUID, *extra) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.tenant_id == tenant_id, *extra)
            .execution_options(**_NO_FILTER)
        )
    ) or 0


async def assert_can_add_product(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    plan = await plan_for(session, tenant_id)
    if plan is None or plan.max_products is None:
        return
    current = await _count(session, Product, tenant_id, Product.deleted_at.is_(None))
    if current >= plan.max_products:
        raise QuotaExceededError(
            f"The {plan.name} plan allows {plan.max_products} products. " "Upgrade to add more.",
            details={"limit": plan.max_products, "current": current, "resource": "products"},
        )


async def assert_can_add_user(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    plan = await plan_for(session, tenant_id)
    if plan is None or plan.max_users is None:
        return
    current = await _count(session, User, tenant_id, User.deleted_at.is_(None))
    if current >= plan.max_users:
        raise QuotaExceededError(
            f"The {plan.name} plan allows {plan.max_users} staff accounts. " "Upgrade to add more.",
            details={"limit": plan.max_users, "current": current, "resource": "users"},
        )


async def assert_can_add_branch(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    plan = await plan_for(session, tenant_id)
    if plan is None or plan.max_branches is None:
        return
    current = await _count(session, Branch, tenant_id, Branch.deleted_at.is_(None))
    if current >= plan.max_branches:
        raise QuotaExceededError(
            f"The {plan.name} plan allows {plan.max_branches} "
            f"branch{'es' if plan.max_branches != 1 else ''}. Upgrade to add more.",
            details={"limit": plan.max_branches, "current": current, "resource": "branches"},
        )


async def usage_summary(session: AsyncSession, tenant_id: uuid.UUID) -> dict:
    """Powers the billing screen's usage bars.

    Shown before the limit is hit, because discovering a plan ceiling at the
    moment you need to add a till is a bad way to find out.
    """
    plan = await plan_for(session, tenant_id)
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return {
        "plan_name": plan.name if plan else None,
        "products": {
            "used": await _count(session, Product, tenant_id, Product.deleted_at.is_(None)),
            "limit": plan.max_products if plan else None,
        },
        "users": {
            "used": await _count(session, User, tenant_id, User.deleted_at.is_(None)),
            "limit": plan.max_users if plan else None,
        },
        "branches": {
            "used": await _count(session, Branch, tenant_id, Branch.deleted_at.is_(None)),
            "limit": plan.max_branches if plan else None,
        },
        "orders_this_month": {
            "used": await _count(
                session,
                Order,
                tenant_id,
                Order.status != OrderStatus.DRAFT,
                Order.created_at >= month_start,
            ),
            "limit": plan.max_orders_per_month if plan else None,
        },
    }
