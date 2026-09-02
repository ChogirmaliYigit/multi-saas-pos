from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BillingCycle, InvoiceStatus, SubscriptionStatus

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class Plan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A pricing tier owned by the SaaS operator. Global, not tenant-scoped."""

    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True
    )  # basic|pro|enterprise
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    price_monthly: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    price_yearly: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)

    # Hard limits enforced by the quota guard on create endpoints.
    # NULL means unlimited.
    max_branches: Mapped[int | None] = mapped_column(Integer)
    max_users: Mapped[int | None] = mapped_column(Integer)
    max_products: Mapped[int | None] = mapped_column(Integer)
    max_orders_per_month: Mapped[int | None] = mapped_column(Integer)

    # Boolean feature switches: {"pdf_reports": true, "multi_branch": true, ...}
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="plan")


class Subscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One active subscription per tenant. Source of truth for MRR."""

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_subscriptions_tenant"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )

    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        nullable=False,
        default=SubscriptionStatus.TRIALING,
        index=True,
    )
    billing_cycle: Mapped[BillingCycle] = mapped_column(
        Enum(BillingCycle, name="billing_cycle"), nullable=False, default=BillingCycle.MONTHLY
    )

    # Price is frozen at subscribe time so a later plan price change does not
    # silently re-bill existing tenants.
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    external_provider: Mapped[str | None] = mapped_column(String(32))  # stripe, paddle...
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)

    tenant: Mapped[Tenant] = relationship(back_populates="subscription")
    plan: Mapped[Plan] = relationship(back_populates="subscriptions")
    invoices: Mapped[list[SubscriptionInvoice]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )

    @property
    def monthly_recurring_revenue(self) -> Decimal:
        """Normalises yearly plans to a monthly figure for the MRR dashboard."""
        if self.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE):
            return Decimal("0.00")
        if self.billing_cycle is BillingCycle.YEARLY:
            return (self.unit_amount / Decimal(12)).quantize(Decimal("0.01"))
        return self.unit_amount


class SubscriptionInvoice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Billing history for the SaaS owner. Not the customer's sales receipts."""

    __tablename__ = "subscription_invoices"
    __table_args__ = (UniqueConstraint("number", name="uq_subscription_invoices_number"),)

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status"), nullable=False, default=InvoiceStatus.OPEN
    )
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subscription: Mapped[Subscription] = relationship(back_populates="invoices")
