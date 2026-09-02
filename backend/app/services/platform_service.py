"""Cross-tenant queries for the SaaS operator.

Everything here deliberately reads across shops, which is exactly what the
rest of the codebase spends three layers preventing. Two things make that safe:

  * these functions are only reachable behind the `PlatformAdmin` dependency,
    which requires a signature-verified SUPER_ADMIN token; and
  * the RLS escape is a named GUC set only by `get_db` for that same verified
    principal, so a tenant request cannot reach this data even if it somehow
    called these functions.

The ORM tenant filter is a no-op here because a platform admin has no
tenant_id, so no `SKIP_TENANT_FILTER` is needed -- but RLS still applies, and
`app.is_platform` is what lets these queries see more than nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Numeric, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Product
from app.models.enums import OrderStatus, SubscriptionStatus, TenantStatus
from app.models.sales import Order
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.platform import MrrPoint, PlatformMetrics, TenantSummary

ZERO = Decimal("0")

# Subscriptions that are actually billing. Trials contribute nothing to MRR --
# counting them is how a SaaS dashboard ends up flattering itself.
BILLING_STATUSES = [SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE]

# Yearly plans normalise to a monthly figure so the two cycles are comparable.
_MONTHLY_AMOUNT = case(
    (
        Subscription.billing_cycle == "YEARLY",
        cast(Subscription.unit_amount, Numeric(14, 4)) / 12,
    ),
    else_=cast(Subscription.unit_amount, Numeric(14, 4)),
)


def _month_start(when: datetime) -> datetime:
    return when.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def metrics(session: AsyncSession) -> PlatformMetrics:
    now = datetime.now(UTC)
    month_start = _month_start(now)
    thirty_days_ago = now - timedelta(days=30)

    counts = (
        await session.execute(
            select(
                func.count(Tenant.id),
                func.count(Tenant.id).filter(Tenant.status == TenantStatus.ACTIVE),
                func.count(Tenant.id).filter(Tenant.status == TenantStatus.TRIAL),
                func.count(Tenant.id).filter(Tenant.status == TenantStatus.SUSPENDED),
                func.count(Tenant.id).filter(Tenant.created_at >= month_start),
            ).where(Tenant.deleted_at.is_(None))
        )
    ).one()

    mrr = Decimal(
        (
            await session.scalar(
                select(func.coalesce(func.sum(_MONTHLY_AMOUNT), 0)).where(
                    Subscription.status.in_(BILLING_STATUSES)
                )
            )
        )
        or 0
    ).quantize(Decimal("0.01"))

    trial_pipeline = Decimal(
        (
            await session.scalar(
                select(func.coalesce(func.sum(_MONTHLY_AMOUNT), 0)).where(
                    Subscription.status == SubscriptionStatus.TRIALING
                )
            )
        )
        or 0
    ).quantize(Decimal("0.01"))

    churned = (
        await session.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.canceled_at.is_not(None),
                Subscription.canceled_at >= month_start,
            )
        )
    ) or 0

    total_users = (
        await session.scalar(
            select(func.count(User.id)).where(
                User.deleted_at.is_(None), User.tenant_id.is_not(None)
            )
        )
    ) or 0

    trading = (
        await session.execute(
            select(
                func.count(Order.id),
                func.coalesce(func.sum(Order.total), 0),
            ).where(
                Order.status.in_([OrderStatus.COMPLETED, OrderStatus.PARTIALLY_REFUNDED]),
                Order.completed_at >= thirty_days_ago,
            )
        )
    ).one()

    return PlatformMetrics(
        total_tenants=counts[0],
        active_tenants=counts[1],
        trialing_tenants=counts[2],
        suspended_tenants=counts[3],
        mrr=mrr,
        arr=(mrr * 12).quantize(Decimal("0.01")),
        trial_pipeline_mrr=trial_pipeline,
        # Every plan is priced in one currency today; when that stops being
        # true this needs an FX layer rather than a bare sum.
        currency="USD",
        new_tenants_this_month=counts[4],
        churned_this_month=churned,
        total_users=total_users,
        orders_last_30_days=trading[0],
        gmv_last_30_days=Decimal(trading[1]),
    )


async def mrr_series(session: AsyncSession, months: int = 12) -> list[MrrPoint]:
    """MRR by month.

    Approximated from each subscription's current amount against the months it
    was live. Exact historical MRR needs a subscription-events table (every
    upgrade, downgrade and pause); this is honest enough for a trend line and
    is labelled as such in the UI.
    """
    now = datetime.now(UTC)
    points: list[MrrPoint] = []

    for offset in range(months - 1, -1, -1):
        # Walk back whole months without dateutil.
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        bucket_start = datetime(year, month, 1, tzinfo=UTC)
        bucket_end = (
            datetime(year + 1, 1, 1, tzinfo=UTC)
            if month == 12
            else datetime(year, month + 1, 1, tzinfo=UTC)
        )

        row = (
            await session.execute(
                select(
                    func.coalesce(func.sum(_MONTHLY_AMOUNT), 0),
                    func.count(Subscription.id),
                ).where(
                    Subscription.status.in_(BILLING_STATUSES),
                    Subscription.current_period_start < bucket_end,
                    (Subscription.canceled_at.is_(None))
                    | (Subscription.canceled_at >= bucket_start),
                )
            )
        ).one()

        points.append(
            MrrPoint(
                month=bucket_start.date(),
                mrr=Decimal(row[0]).quantize(Decimal("0.01")),
                tenants=row[1],
            )
        )

    return points


async def list_tenants(
    session: AsyncSession,
    *,
    search: str | None = None,
    status: TenantStatus | None = None,
    offset: int = 0,
    limit: int = 25,
) -> tuple[list[TenantSummary], int]:
    """Shops with their plan and usage.

    One grouped query per aggregate rather than per-row lookups: at a thousand
    tenants the N+1 version is a thousand round trips to render one page.
    """
    conditions = [Tenant.deleted_at.is_(None)]
    if status:
        conditions.append(Tenant.status == status)
    if search:
        term = f"%{search.lower()}%"
        conditions.append(
            func.lower(Tenant.name).like(term)
            | func.lower(Tenant.slug).like(term)
            | func.lower(Tenant.email).like(term)
        )

    total = (await session.scalar(select(func.count()).select_from(Tenant).where(*conditions))) or 0

    rows = (
        await session.execute(
            select(Tenant, Subscription, Plan)
            .outerjoin(Subscription, Subscription.tenant_id == Tenant.id)
            .outerjoin(Plan, Plan.id == Subscription.plan_id)
            .where(*conditions)
            .order_by(Tenant.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    tenant_ids = [row[0].id for row in rows]
    if not tenant_ids:
        return [], total

    users_by_tenant = dict(
        (
            await session.execute(
                select(User.tenant_id, func.count(User.id))
                .where(User.tenant_id.in_(tenant_ids), User.deleted_at.is_(None))
                .group_by(User.tenant_id)
            )
        ).all()
    )
    products_by_tenant = dict(
        (
            await session.execute(
                select(Product.tenant_id, func.count(Product.id))
                .where(Product.tenant_id.in_(tenant_ids), Product.deleted_at.is_(None))
                .group_by(Product.tenant_id)
            )
        ).all()
    )

    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    trading_by_tenant = {
        row[0]: (row[1], Decimal(row[2]), row[3])
        for row in (
            await session.execute(
                select(
                    Order.tenant_id,
                    func.count(Order.id),
                    func.coalesce(func.sum(Order.total), 0),
                    func.max(Order.completed_at),
                )
                .where(
                    Order.tenant_id.in_(tenant_ids),
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.PARTIALLY_REFUNDED]),
                    Order.completed_at >= thirty_days_ago,
                )
                .group_by(Order.tenant_id)
            )
        ).all()
    }

    summaries = []
    for tenant, subscription, plan in rows:
        orders, gmv, last_seen = trading_by_tenant.get(tenant.id, (0, ZERO, None))
        summaries.append(
            TenantSummary(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                email=tenant.email,
                status=tenant.status,
                currency=tenant.currency,
                country_code=tenant.country_code,
                created_at=tenant.created_at,
                trial_ends_at=tenant.trial_ends_at,
                blocked_reason=tenant.blocked_reason,
                plan_name=plan.name if plan else None,
                plan_code=plan.code if plan else None,
                subscription_status=subscription.status if subscription else None,
                billing_cycle=subscription.billing_cycle if subscription else None,
                mrr=(subscription.monthly_recurring_revenue if subscription else ZERO),
                user_count=users_by_tenant.get(tenant.id, 0),
                product_count=products_by_tenant.get(tenant.id, 0),
                orders_last_30_days=orders,
                gmv_last_30_days=gmv,
                last_activity_at=last_seen,
            )
        )

    return summaries, total


async def plans_with_usage(session: AsyncSession) -> list[dict]:
    """Plans plus how many shops are on each -- the number that decides
    whether a price change is safe to make."""
    usage = {
        row[0]: (row[1], Decimal(row[2]).quantize(Decimal("0.01")))
        for row in (
            await session.execute(
                select(
                    Subscription.plan_id,
                    func.count(Subscription.id),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    Subscription.status.in_(BILLING_STATUSES),
                                    _MONTHLY_AMOUNT,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).group_by(Subscription.plan_id)
            )
        ).all()
    }

    plans = await session.scalars(select(Plan).order_by(Plan.sort_order, Plan.name))
    return [
        {
            "plan": plan,
            "subscriber_count": usage.get(plan.id, (0, ZERO))[0],
            "mrr": usage.get(plan.id, (0, ZERO))[1],
        }
        for plan in plans
    ]


async def tenant_or_none(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    return await session.scalar(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
