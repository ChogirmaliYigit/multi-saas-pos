from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import CurrentTenant, DbSession, require
from app.core.config import settings
from app.core.permissions import Permission
from app.db.tenant_filter import SKIP_TENANT_FILTER
from app.models.enums import InvoiceStatus
from app.models.subscription import Plan, Subscription, SubscriptionInvoice
from app.schemas.billing import BillingOverview, InvoiceOut, PayLink
from app.services.gateways import click as click_gateway
from app.services.gateways import payme as payme_gateway

router = APIRouter(prefix="/billing", tags=["billing"])

_NO_FILTER = {SKIP_TENANT_FILTER: True}


def _pay_links(invoice: SubscriptionInvoice) -> list[PayLink]:
    """Only offer a gateway that is actually configured.

    A dead payment button is worse than no button: the shop assumes their
    card failed rather than that nobody wired up the provider.
    """
    links: list[PayLink] = []
    return_url = f"{settings.APP_BASE_URL.rstrip('/')}/billing"

    if settings.payme_configured:
        links.append(
            PayLink(
                provider="payme",
                label="Payme",
                url=payme_gateway.checkout_url(str(invoice.id), invoice.amount_due, return_url),
            )
        )
    if settings.click_configured:
        links.append(
            PayLink(
                provider="click",
                label="Click",
                url=click_gateway.checkout_url(str(invoice.id), invoice.amount_due, return_url),
            )
        )
    return links


@router.get(
    "",
    response_model=BillingOverview,
    dependencies=[Depends(require(Permission.BILLING_READ))],
)
async def overview(db: DbSession, tenant: CurrentTenant) -> BillingOverview:
    subscription = await db.scalar(
        select(Subscription)
        .where(Subscription.tenant_id == tenant.id)
        .execution_options(**_NO_FILTER)
    )
    plan = (
        await db.scalar(
            select(Plan).where(Plan.id == subscription.plan_id).execution_options(**_NO_FILTER)
        )
        if subscription
        else None
    )

    invoices = list(
        await db.scalars(
            select(SubscriptionInvoice)
            .where(SubscriptionInvoice.tenant_id == tenant.id)
            .order_by(SubscriptionInvoice.issued_at.desc())
            .limit(24)
            .execution_options(**_NO_FILTER)
        )
    )
    outstanding = next((i for i in invoices if i.status is InvoiceStatus.OPEN), None)

    grace_remaining = None
    if outstanding is not None:
        deadline = outstanding.issued_at + timedelta(days=settings.BILLING_GRACE_DAYS)
        grace_remaining = (deadline - datetime.now(UTC)).days

    return BillingOverview(
        plan_name=plan.name if plan else None,
        plan_code=plan.code if plan else None,
        status=subscription.status if subscription else None,
        billing_cycle=subscription.billing_cycle if subscription else None,
        amount=subscription.unit_amount if subscription else Decimal("0"),
        currency=subscription.currency if subscription else tenant.currency,
        current_period_end=subscription.current_period_end if subscription else None,
        trial_ends_at=tenant.trial_ends_at,
        cancel_at_period_end=subscription.cancel_at_period_end if subscription else False,
        tenant_status=tenant.status,
        grace_days_remaining=grace_remaining,
        outstanding=InvoiceOut.model_validate(outstanding) if outstanding else None,
        pay_links=_pay_links(outstanding) if outstanding else [],
        invoices=[InvoiceOut.model_validate(i) for i in invoices],
    )


# ---------------------------------------------------------------------------
# Gateway callbacks
#
# These are the only unauthenticated write endpoints in the system. They are
# not protected by a session, because the caller is a payment provider that
# has none -- authentication is the provider's own scheme: HTTP Basic for
# Payme, an MD5 signature for Click, both verified inside the adapters before
# anything is written.
#
# A suspended tenant does not block them either: paying is exactly how a
# suspended shop is meant to get back.
# ---------------------------------------------------------------------------


@router.post("/payme", include_in_schema=False)
async def payme_callback(request: Request, db: DbSession) -> dict:
    """Payme's single JSON-RPC endpoint.

    Always 200 with a JSON-RPC envelope, errors included: Payme reads a
    non-200 as a transport failure and retries forever, turning a permanent
    rejection into a loop.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    return await payme_gateway.dispatch(db, body, request.headers.get("authorization"))


@router.post("/click/prepare", include_in_schema=False)
async def click_prepare(request: Request, db: DbSession) -> dict:
    """Click sends form-encoded fields, not JSON."""
    form = dict(await request.form())
    return await click_gateway.prepare(db, form)


@router.post("/click/complete", include_in_schema=False)
async def click_complete(request: Request, db: DbSession) -> dict:
    form = dict(await request.form())
    return await click_gateway.complete(db, form)
