"""Subscription billing, independent of any gateway.

Payme and Click describe the same lifecycle in different vocabularies. This
module owns the lifecycle; the adapters translate at the edge. Nothing here
knows what a tiyin is.

The money rule from checkout applies again: an amount is derived from the
subscription, never taken from a gateway's request. A provider that could
name the amount could name a smaller one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import APIError, NotFoundError
from app.db.tenant_filter import SKIP_TENANT_FILTER
from app.models.enums import (
    BillingCycle,
    InvoiceStatus,
    SubscriptionStatus,
    TenantStatus,
    TransactionState,
)
from app.models.subscription import (
    PaymentTransaction,
    Subscription,
    SubscriptionInvoice,
)
from app.models.tenant import Tenant

_NO_FILTER = {SKIP_TENANT_FILTER: True}
ZERO = Decimal("0.00")


class InvoiceNotPayableError(APIError):
    status_code = 409
    code = "invoice_not_payable"
    message = "That invoice cannot be paid."


def _now() -> datetime:
    return datetime.now(UTC)


def period_length(cycle: BillingCycle) -> timedelta:
    return timedelta(days=365 if cycle is BillingCycle.YEARLY else 30)


async def _next_invoice_number(session: AsyncSession, when: datetime) -> str:
    """Sequential per month: INV-202609-0001.

    Not per tenant -- these are the operator's own sales records, and an
    accountant wants one unbroken series across the whole platform.
    """
    prefix = f"INV-{when:%Y%m}-"
    used = await session.scalar(
        select(func.count(SubscriptionInvoice.id))
        .where(SubscriptionInvoice.number.like(f"{prefix}%"))
        .execution_options(**_NO_FILTER)
    )
    return f"{prefix}{(used or 0) + 1:04d}"


async def issue_invoice(session: AsyncSession, subscription: Subscription) -> SubscriptionInvoice:
    """Create the invoice for the subscription's current period.

    Idempotent per period: calling it twice does not bill twice, which
    matters because the daily task retries after any failure.
    """
    existing = await session.scalar(
        select(SubscriptionInvoice)
        .where(
            SubscriptionInvoice.subscription_id == subscription.id,
            SubscriptionInvoice.period_start == subscription.current_period_start,
            SubscriptionInvoice.status != InvoiceStatus.VOID,
        )
        .execution_options(**_NO_FILTER)
    )
    if existing is not None:
        return existing

    now = _now()
    invoice = SubscriptionInvoice(
        subscription_id=subscription.id,
        tenant_id=subscription.tenant_id,
        number=await _next_invoice_number(session, now),
        status=InvoiceStatus.OPEN,
        # From the subscription's frozen amount, never from a request.
        amount_due=subscription.unit_amount,
        amount_paid=ZERO,
        currency=subscription.currency,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        issued_at=now,
    )
    session.add(invoice)
    await session.flush()
    return invoice


async def find_invoice(session: AsyncSession, invoice_id: uuid.UUID) -> SubscriptionInvoice | None:
    """Look up an invoice without a tenant context.

    Gateways arrive with no session, so this deliberately bypasses the ORM
    tenant filter. Every caller re-derives the tenant from the row rather
    than trusting anything the gateway sent.
    """
    return await session.scalar(
        select(SubscriptionInvoice)
        .where(SubscriptionInvoice.id == invoice_id)
        .execution_options(**_NO_FILTER)
    )


async def assert_payable(
    session: AsyncSession, invoice: SubscriptionInvoice, amount: Decimal
) -> None:
    """The checks every gateway needs before it will show a payment form."""
    if invoice.status is InvoiceStatus.PAID:
        raise InvoiceNotPayableError("That invoice is already paid.", code="already_paid")
    if invoice.status in (InvoiceStatus.VOID, InvoiceStatus.UNCOLLECTIBLE):
        raise InvoiceNotPayableError("That invoice has been cancelled.", code="void")
    if amount != invoice.amount_due:
        raise InvoiceNotPayableError(
            "Wrong amount.",
            code="wrong_amount",
            details={"expected": str(invoice.amount_due), "received": str(amount)},
        )


async def mark_paid(session: AsyncSession, transaction: PaymentTransaction) -> SubscriptionInvoice:
    """Settle an invoice and roll the subscription forward.

    Idempotent: a gateway that calls PerformTransaction twice -- which both
    Payme and Click do -- must not extend the period twice.
    """
    invoice = await find_invoice(session, transaction.invoice_id)
    if invoice is None:
        raise NotFoundError("Invoice not found.")

    if invoice.status is InvoiceStatus.PAID:
        return invoice

    now = _now()
    invoice.status = InvoiceStatus.PAID
    invoice.amount_paid = transaction.amount
    invoice.paid_at = now

    subscription = await session.scalar(
        select(Subscription)
        .where(Subscription.id == invoice.subscription_id)
        .execution_options(**_NO_FILTER)
    )
    if subscription is not None:
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.canceled_at = None
        # Extend from the period that was just paid for, not from today: a
        # shop that pays three days late should not lose those three days.
        base = max(subscription.current_period_end, invoice.period_end)
        subscription.current_period_start = base
        subscription.current_period_end = base + period_length(subscription.billing_cycle)

        tenant = await session.scalar(
            select(Tenant)
            .where(Tenant.id == subscription.tenant_id)
            .execution_options(**_NO_FILTER)
        )
        if tenant is not None and tenant.status in (
            TenantStatus.SUSPENDED,
            TenantStatus.TRIAL,
        ):
            # Paying reopens a shop that was suspended for non-payment.
            tenant.status = TenantStatus.ACTIVE
            tenant.blocked_reason = None
            tenant.trial_ends_at = None

    await session.flush()
    return invoice


async def mark_refunded(session: AsyncSession, transaction: PaymentTransaction) -> None:
    """A gateway reversed a settled payment.

    The invoice reopens rather than voiding: the debt is still owed, it was
    just not collected. The daily sweep then treats it like any other unpaid
    invoice, grace period included.
    """
    invoice = await find_invoice(session, transaction.invoice_id)
    if invoice is None:
        return

    invoice.status = InvoiceStatus.OPEN
    invoice.amount_paid = ZERO
    invoice.paid_at = None

    subscription = await session.scalar(
        select(Subscription)
        .where(Subscription.id == invoice.subscription_id)
        .execution_options(**_NO_FILTER)
    )
    if subscription is not None:
        subscription.status = SubscriptionStatus.PAST_DUE
    await session.flush()


async def run_billing_cycle(session: AsyncSession) -> dict[str, int]:
    """The daily sweep: invoice, chase, then suspend.

    Three stages, in this order, so a shop is never suspended in the same run
    that first invoiced it.
    """
    now = _now()
    issued = past_due = suspended = 0

    # 1. Subscriptions whose period has ended get an invoice.
    due = await session.scalars(
        select(Subscription)
        .where(
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE]),
            Subscription.current_period_end <= now,
            Subscription.cancel_at_period_end.is_(False),
        )
        .execution_options(**_NO_FILTER)
    )
    for subscription in due.all():
        await issue_invoice(session, subscription)
        if subscription.status is SubscriptionStatus.ACTIVE:
            subscription.status = SubscriptionStatus.PAST_DUE
            past_due += 1
        issued += 1

    # 2. Anything unpaid past the grace period suspends the shop.
    cutoff = now - timedelta(days=settings.BILLING_GRACE_DAYS)
    overdue = await session.scalars(
        select(SubscriptionInvoice)
        .where(
            SubscriptionInvoice.status == InvoiceStatus.OPEN,
            SubscriptionInvoice.issued_at <= cutoff,
        )
        .execution_options(**_NO_FILTER)
    )
    for invoice in overdue.all():
        tenant = await session.scalar(
            select(Tenant)
            .where(Tenant.id == invoice.tenant_id, Tenant.deleted_at.is_(None))
            .execution_options(**_NO_FILTER)
        )
        if tenant is None or tenant.status is TenantStatus.SUSPENDED:
            continue
        tenant.status = TenantStatus.SUSPENDED
        tenant.blocked_reason = f"Invoice {invoice.number} is unpaid. Settle it to resume trading."
        suspended += 1

    await session.flush()
    return {"invoiced": issued, "past_due": past_due, "suspended": suspended}


async def record_transaction(
    session: AsyncSession,
    *,
    invoice: SubscriptionInvoice,
    provider,
    external_id: str,
    amount: Decimal,
    created_time: int | None = None,
    payload: dict | None = None,
) -> PaymentTransaction:
    """Create or return the transaction for a provider's id.

    Both gateways resend the same id, so this is a get-or-create rather than
    an insert: a duplicate CreateTransaction must return the original.
    """
    existing = await session.scalar(
        select(PaymentTransaction)
        .where(
            PaymentTransaction.provider == provider,
            PaymentTransaction.external_id == external_id,
        )
        .execution_options(**_NO_FILTER)
    )
    if existing is not None:
        return existing

    transaction = PaymentTransaction(
        invoice_id=invoice.id,
        tenant_id=invoice.tenant_id,
        provider=provider,
        external_id=external_id,
        state=TransactionState.CREATED,
        amount=amount,
        currency=invoice.currency,
        created_time=created_time,
        payload=payload or {},
    )
    session.add(transaction)
    await session.flush()
    return transaction


async def find_transaction(
    session: AsyncSession, *, provider, external_id: str
) -> PaymentTransaction | None:
    return await session.scalar(
        select(PaymentTransaction)
        .where(
            PaymentTransaction.provider == provider,
            PaymentTransaction.external_id == external_id,
        )
        .execution_options(**_NO_FILTER)
    )
