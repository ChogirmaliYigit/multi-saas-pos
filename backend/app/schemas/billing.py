from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import (
    BillingCycle,
    InvoiceStatus,
    SubscriptionStatus,
    TenantStatus,
)
from app.schemas.common import ORMModel


class InvoiceOut(ORMModel):
    id: uuid.UUID
    number: str
    status: InvoiceStatus
    amount_due: Decimal
    amount_paid: Decimal
    currency: str
    period_start: datetime
    period_end: datetime
    issued_at: datetime
    paid_at: datetime | None


class PayLink(BaseModel):
    provider: str
    label: str
    url: str


class BillingOverview(BaseModel):
    """What a shop owner needs on the billing page."""

    plan_name: str | None
    plan_code: str | None
    status: SubscriptionStatus | None
    billing_cycle: BillingCycle | None
    amount: Decimal
    currency: str
    current_period_end: datetime | None
    trial_ends_at: datetime | None
    cancel_at_period_end: bool

    tenant_status: TenantStatus
    # Days left before an unpaid invoice suspends the shop. Negative once it
    # already has.
    grace_days_remaining: int | None

    outstanding: InvoiceOut | None
    pay_links: list[PayLink] = []
    invoices: list[InvoiceOut] = []
