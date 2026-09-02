from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import DbSession, PlatformAdmin
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import session_tenant_scope
from app.models.enums import (
    BillingCycle,
    SubscriptionStatus,
    TenantStatus,
)
from app.models.subscription import Plan, Subscription
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.platform import (
    MrrPoint,
    PlanIn,
    PlanOut,
    PlanUpdate,
    PlatformMetrics,
    TenantCreate,
    TenantPlanUpdate,
    TenantStatusUpdate,
    TenantSummary,
)
from app.services import auth_service, platform_service

# Every route here sits behind PlatformAdmin. A tenant user probing this path
# gets the same 403 as any other denial -- the API does not confirm that a
# platform surface exists at all.
router = APIRouter(prefix="/platform", tags=["platform"])


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@router.get("/metrics", response_model=PlatformMetrics)
async def metrics(db: DbSession, _: PlatformAdmin) -> PlatformMetrics:
    return await platform_service.metrics(db)


@router.get("/mrr", response_model=list[MrrPoint])
async def mrr(
    db: DbSession,
    _: PlatformAdmin,
    months: int = Query(12, ge=1, le=36),
) -> list[MrrPoint]:
    return await platform_service.mrr_series(db, months)


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------


@router.get("/tenants", response_model=Page[TenantSummary])
async def list_tenants(
    db: DbSession,
    _: PlatformAdmin,
    search: str | None = Query(default=None, max_length=100),
    tenant_status: TenantStatus | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
) -> Page[TenantSummary]:
    items, total = await platform_service.list_tenants(
        db,
        search=search,
        status=tenant_status,
        offset=(page - 1) * size,
        limit=size,
    )
    return Page[TenantSummary](items=items, total=total, page=page, size=size)


@router.get("/tenants/{tenant_id}", response_model=TenantSummary)
async def get_tenant(tenant_id: uuid.UUID, db: DbSession, _: PlatformAdmin) -> TenantSummary:
    items, _total = await platform_service.list_tenants(db, limit=1000)
    for item in items:
        if item.id == tenant_id:
            return item
    raise NotFoundError("Shop not found.")


@router.post("/tenants", response_model=TenantSummary, status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, db: DbSession, _: PlatformAdmin) -> TenantSummary:
    """Create a shop on behalf of a customer -- sales-assisted onboarding.

    Reuses the signup path rather than duplicating it, so a shop created here
    is identical to one that self-registered: same default branch, same trial
    subscription, same owner role.
    """
    from app.schemas.auth import SignupRequest

    signup = SignupRequest(
        shop_name=payload.shop_name,
        slug=payload.slug,
        owner_name=payload.owner_name,
        email=payload.email,
        password=payload.password,
        currency=payload.currency,
        country_code=payload.country_code,
        timezone=payload.timezone,
        plan_code=payload.plan_code,
    )
    tenant, _owner = await auth_service.signup(db, signup)
    await db.flush()

    items, _total = await platform_service.list_tenants(db, search=tenant.slug, limit=1)
    if not items:  # pragma: no cover - the row was just written
        raise NotFoundError("Shop was created but could not be read back.")
    return items[0]


@router.patch("/tenants/{tenant_id}/status", response_model=TenantSummary)
async def set_tenant_status(
    tenant_id: uuid.UUID,
    payload: TenantStatusUpdate,
    db: DbSession,
    admin: PlatformAdmin,
) -> TenantSummary:
    """Block or unblock a shop.

    Takes effect on the very next request: `get_current_tenant` checks the
    status on every call, so a suspended shop is cut off immediately rather
    than whenever its staff happen to have their tokens expire. Existing
    sessions are also revoked, so a till already open cannot keep trading.
    """
    tenant = await platform_service.tenant_or_none(db, tenant_id)
    if tenant is None:
        raise NotFoundError("Shop not found.")

    tenant.status = payload.status
    tenant.blocked_reason = payload.reason if payload.status == TenantStatus.SUSPENDED else None

    if payload.status in (TenantStatus.SUSPENDED, TenantStatus.CANCELLED):
        staff = await db.scalars(
            select(User).where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
        )
        for member in staff:
            await auth_service._revoke_all_for_user(db, member.id)

    await db.flush()
    return await get_tenant(tenant_id, db, admin)


@router.patch("/tenants/{tenant_id}/plan", response_model=TenantSummary)
async def change_tenant_plan(
    tenant_id: uuid.UUID,
    payload: TenantPlanUpdate,
    db: DbSession,
    admin: PlatformAdmin,
) -> TenantSummary:
    tenant = await platform_service.tenant_or_none(db, tenant_id)
    if tenant is None:
        raise NotFoundError("Shop not found.")

    plan = await db.scalar(select(Plan).where(Plan.id == payload.plan_id))
    if plan is None:
        raise NotFoundError("Plan not found.", code="plan_not_found")

    subscription = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    now = datetime.now(UTC)

    amount = (
        plan.price_yearly if payload.billing_cycle is BillingCycle.YEARLY else plan.price_monthly
    )
    period_end = now + timedelta(days=365 if payload.billing_cycle is BillingCycle.YEARLY else 30)

    if subscription is None:
        async with session_tenant_scope(db, tenant_id):
            db.add(
                Subscription(
                    tenant_id=tenant_id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.ACTIVE,
                    billing_cycle=payload.billing_cycle,
                    unit_amount=amount,
                    currency=plan.currency,
                    current_period_start=now,
                    current_period_end=period_end,
                )
            )
    else:
        subscription.plan_id = plan.id
        subscription.billing_cycle = payload.billing_cycle
        # Re-price at the plan's current list price. This is the one place a
        # tenant's frozen amount is intentionally refreshed.
        subscription.unit_amount = amount
        subscription.currency = plan.currency

        reviving = subscription.status in (
            SubscriptionStatus.CANCELED,
            SubscriptionStatus.EXPIRED,
        )
        if reviving or payload.activate:
            # Converting a trial is deliberate: it is the moment the shop
            # starts paying, and it moves them from pipeline into MRR.
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.canceled_at = None
            subscription.current_period_start = now
            subscription.current_period_end = period_end
            if tenant.status is TenantStatus.TRIAL:
                tenant.status = TenantStatus.ACTIVE
                tenant.trial_ends_at = None

    # Deliberately NOT trimming products or staff that exceed the new plan's
    # limits: a downgrade must never silently delete a shop's data. The quota
    # guard simply refuses further additions until they are back under.
    await db.flush()
    return await get_tenant(tenant_id, db, admin)


@router.delete("/tenants/{tenant_id}", response_model=Message)
async def delete_tenant(tenant_id: uuid.UUID, db: DbSession, _: PlatformAdmin) -> Message:
    """Soft delete. A hard delete would take the shop's sales history with it,
    which is usually a legal record the operator is required to retain."""
    tenant = await platform_service.tenant_or_none(db, tenant_id)
    if tenant is None:
        raise NotFoundError("Shop not found.")

    tenant.deleted_at = func.now()
    tenant.status = TenantStatus.CANCELLED

    staff = await db.scalars(
        select(User).where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
    )
    for member in staff:
        await auth_service._revoke_all_for_user(db, member.id)

    subscription = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if subscription is not None:
        subscription.status = SubscriptionStatus.CANCELED
        subscription.canceled_at = datetime.now(UTC)

    return Message(message="Shop closed. Its trading history is retained.")


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(db: DbSession, _: PlatformAdmin) -> list[PlanOut]:
    rows = await platform_service.plans_with_usage(db)
    return [
        PlanOut(
            **{
                field: getattr(row["plan"], field)
                for field in PlanOut.model_fields
                if hasattr(row["plan"], field)
            },
            subscriber_count=row["subscriber_count"],
            mrr=row["mrr"],
        )
        for row in rows
    ]


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(payload: PlanIn, db: DbSession, _: PlatformAdmin) -> PlanOut:
    if await db.scalar(select(Plan.id).where(Plan.code == payload.code)):
        raise ConflictError(f"A plan with code {payload.code} exists.", code="code_taken")

    plan = Plan(**payload.model_dump())
    db.add(plan)
    await db.flush()
    return PlanOut.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: uuid.UUID, payload: PlanUpdate, db: DbSession, _: PlatformAdmin
) -> PlanOut:
    """Edit a tier.

    Changing a price here does NOT re-bill existing subscribers: their
    `unit_amount` was frozen when they signed up, precisely so a list-price
    change cannot silently increase what a shop already pays. New signups and
    explicit plan changes pick up the new price.
    """
    plan = await db.scalar(select(Plan).where(Plan.id == plan_id))
    if plan is None:
        raise NotFoundError("Plan not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)

    await db.flush()
    return PlanOut.model_validate(plan)


@router.delete("/plans/{plan_id}", response_model=Message)
async def retire_plan(plan_id: uuid.UUID, db: DbSession, _: PlatformAdmin) -> Message:
    """Retire a plan rather than deleting it.

    Subscriptions reference it with ON DELETE RESTRICT, and a shop mid-term on
    a legacy tier still needs its plan row to resolve. Retiring hides it from
    signup and leaves existing subscribers untouched.
    """
    plan = await db.scalar(select(Plan).where(Plan.id == plan_id))
    if plan is None:
        raise NotFoundError("Plan not found.")

    plan.is_active = False
    plan.is_public = False
    subscribers = (
        await db.scalar(select(func.count(Subscription.id)).where(Subscription.plan_id == plan_id))
    ) or 0

    return Message(
        message=(
            f"Plan retired. {subscribers} existing "
            f"{'shop stays' if subscribers == 1 else 'shops stay'} on it."
        )
    )
