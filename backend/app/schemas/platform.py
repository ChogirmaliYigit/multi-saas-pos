from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import BillingCycle, SubscriptionStatus, TenantStatus
from app.schemas.common import ORMModel


class PlatformMetrics(BaseModel):
    """The SaaS operator's headline numbers."""

    total_tenants: int
    active_tenants: int
    trialing_tenants: int
    suspended_tenants: int
    # MRR counts only subscriptions that are actually billing. Trials are
    # tracked separately as pipeline -- folding them in is how SaaS dashboards
    # end up flattering themselves.
    mrr: Decimal
    arr: Decimal
    trial_pipeline_mrr: Decimal
    currency: str
    new_tenants_this_month: int
    churned_this_month: int
    total_users: int
    orders_last_30_days: int
    gmv_last_30_days: Decimal


class MrrPoint(BaseModel):
    month: date
    mrr: Decimal
    tenants: int


class TenantSummary(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    email: str
    status: TenantStatus
    currency: str
    country_code: str
    created_at: datetime
    trial_ends_at: datetime | None
    blocked_reason: str | None

    plan_name: str | None = None
    plan_code: str | None = None
    subscription_status: SubscriptionStatus | None = None
    billing_cycle: BillingCycle | None = None
    mrr: Decimal = Decimal("0")
    user_count: int = 0
    product_count: int = 0
    orders_last_30_days: int = 0
    gmv_last_30_days: Decimal = Decimal("0")
    last_activity_at: datetime | None = None


class TenantStatusUpdate(BaseModel):
    status: TenantStatus
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def _no_hard_delete(cls, value: TenantStatus) -> TenantStatus:
        return value


class TenantPlanUpdate(BaseModel):
    plan_id: uuid.UUID
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    # Ending a trial starts charging someone, so it is an explicit choice
    # rather than a side effect of assigning a plan. Off by default: an
    # operator fixing a mis-selected tier for a shop still in its trial should
    # not accidentally bill them a fortnight early.
    activate: bool = False


class TenantCreate(BaseModel):
    shop_name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=3, max_length=63)
    owner_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    plan_code: str = "basic"
    currency: str = Field(default="USD", min_length=3, max_length=3)
    country_code: str = Field(default="US", min_length=2, max_length=2)
    timezone: str = "UTC"


class PlanIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=80)
    description: str | None = None
    price_monthly: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    price_yearly: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    trial_days: int = Field(default=14, ge=0, le=365)
    # None means unlimited.
    max_branches: int | None = Field(default=None, ge=1)
    max_users: int | None = Field(default=None, ge=1)
    max_products: int | None = Field(default=None, ge=1)
    max_orders_per_month: int | None = Field(default=None, ge=1)
    features: dict = Field(default_factory=dict)
    is_public: bool = True
    is_active: bool = True
    sort_order: int = 0

    @field_validator("code")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower().strip()


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = None
    price_monthly: Decimal | None = Field(default=None, ge=0)
    price_yearly: Decimal | None = Field(default=None, ge=0)
    trial_days: int | None = Field(default=None, ge=0, le=365)
    max_branches: int | None = Field(default=None, ge=1)
    max_users: int | None = Field(default=None, ge=1)
    max_products: int | None = Field(default=None, ge=1)
    max_orders_per_month: int | None = Field(default=None, ge=1)
    features: dict | None = None
    is_public: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class PlanOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    price_monthly: Decimal
    price_yearly: Decimal
    currency: str
    trial_days: int
    max_branches: int | None
    max_users: int | None
    max_products: int | None
    max_orders_per_month: int | None
    features: dict
    is_public: bool
    is_active: bool
    sort_order: int
    # How many shops are on it -- the number that decides whether a price
    # change is safe.
    subscriber_count: int = 0
    mrr: Decimal = Decimal("0")
