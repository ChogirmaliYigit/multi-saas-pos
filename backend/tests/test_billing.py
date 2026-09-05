"""Subscription billing and the two Uzbek payment gateways.

Money again, so the emphasis is on the ways a gateway can call twice, call
late, or call with the wrong amount.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine, platform_scope
from app.models.enums import InvoiceStatus, SubscriptionStatus, TenantStatus
from app.models.subscription import Subscription, SubscriptionInvoice
from app.models.tenant import Tenant
from app.services import billing_service

SIGNUP = {
    "shop_name": "Corner Store",
    "slug": "corner",
    "owner_name": "Dana Owner",
    "email": "dana@corner.example",
    "password": "correct-horse-battery",
    "plan_code": "basic",
}

PAYME_KEY = "test-payme-key"
CLICK_SECRET = "test-click-secret"


@pytest.fixture(autouse=True)
def _configure_gateways():
    """Credentials the adapters check. Restored afterwards so one test's
    configuration cannot leak into another's."""
    original = (
        settings.PAYME_MERCHANT_ID,
        settings.PAYME_KEY,
        settings.CLICK_SERVICE_ID,
        settings.CLICK_SECRET_KEY,
        settings.CLICK_MERCHANT_ID,
    )
    settings.PAYME_MERCHANT_ID = "merchant-1"
    settings.PAYME_KEY = PAYME_KEY
    settings.CLICK_SERVICE_ID = "svc-1"
    settings.CLICK_SECRET_KEY = CLICK_SECRET
    settings.CLICK_MERCHANT_ID = "click-1"
    yield
    (
        settings.PAYME_MERCHANT_ID,
        settings.PAYME_KEY,
        settings.CLICK_SERVICE_ID,
        settings.CLICK_SECRET_KEY,
        settings.CLICK_MERCHANT_ID,
    ) = original


def payme_auth(key: str = PAYME_KEY) -> dict[str, str]:
    token = base64.b64encode(f"Paycom:{key}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def click_sign(payload: dict, action: str) -> str:
    secret = CLICK_SECRET
    if action == "0":
        raw = (
            f"{payload['click_trans_id']}{payload['service_id']}{secret}"
            f"{payload['merchant_trans_id']}{payload['amount']}"
            f"{payload['action']}{payload['sign_time']}"
        )
    else:
        raw = (
            f"{payload['click_trans_id']}{payload['service_id']}{secret}"
            f"{payload['merchant_trans_id']}{payload['merchant_prepare_id']}"
            f"{payload['amount']}{payload['action']}{payload['sign_time']}"
        )
    return hashlib.md5(raw.encode()).hexdigest()  # noqa: S324


async def shop_with_invoice(client: AsyncClient) -> tuple[dict, str, Decimal]:
    """A signed-up shop with one open invoice. Returns (headers, id, amount)."""
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"], "tenant_slug": "corner"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    async with AsyncSessionLocal() as session, platform_scope(session):
        subscription = await session.scalar(select(Subscription))
        subscription.status = SubscriptionStatus.ACTIVE
        invoice = await billing_service.issue_invoice(session, subscription)
        await session.commit()
        return headers, str(invoice.id), invoice.amount_due


# ---------------------------------------------------------------------------
# Invoicing
# ---------------------------------------------------------------------------


async def test_invoicing_is_idempotent_per_period(client: AsyncClient):
    """The daily task retries after any failure; a retry must not bill twice."""
    await client.post("/api/v1/auth/signup", json=SIGNUP)

    async with AsyncSessionLocal() as session, platform_scope(session):
        subscription = await session.scalar(select(Subscription))
        first = await billing_service.issue_invoice(session, subscription)
        second = await billing_service.issue_invoice(session, subscription)
        await session.commit()
        assert first.id == second.id

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        count = await conn.scalar(text("SELECT count(*) FROM subscription_invoices"))
    assert count == 1


async def test_billing_cycle_invoices_then_suspends_after_grace(
    client: AsyncClient,
):
    """A shop is never suspended in the same run that first invoiced it."""
    await client.post("/api/v1/auth/signup", json=SIGNUP)

    async with AsyncSessionLocal() as session, platform_scope(session):
        subscription = await session.scalar(select(Subscription))
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.current_period_end = datetime.now(UTC) - timedelta(days=1)
        await session.commit()

    async with AsyncSessionLocal() as session, platform_scope(session):
        first = await billing_service.run_billing_cycle(session)
        await session.commit()
    assert first["invoiced"] == 1
    assert first["suspended"] == 0, "suspended on the same run that invoiced"

    async with AsyncSessionLocal() as session, platform_scope(session):
        tenant = await session.scalar(select(Tenant))
        assert tenant.status is not TenantStatus.SUSPENDED

        # Age the invoice past the grace window.
        invoice = await session.scalar(select(SubscriptionInvoice))
        invoice.issued_at = datetime.now(UTC) - timedelta(days=settings.BILLING_GRACE_DAYS + 1)
        await session.commit()

    async with AsyncSessionLocal() as session, platform_scope(session):
        second = await billing_service.run_billing_cycle(session)
        await session.commit()
    assert second["suspended"] == 1

    async with AsyncSessionLocal() as session, platform_scope(session):
        tenant = await session.scalar(select(Tenant))
        assert tenant.status is TenantStatus.SUSPENDED
        assert "unpaid" in (tenant.blocked_reason or "")


async def test_a_suspended_shop_really_cannot_trade(client: AsyncClient):
    """The grace period has to end in something, or it is just a warning."""
    headers, _invoice_id, _amount = await shop_with_invoice(client)

    async with AsyncSessionLocal() as session, platform_scope(session):
        invoice = await session.scalar(select(SubscriptionInvoice))
        invoice.issued_at = datetime.now(UTC) - timedelta(days=settings.BILLING_GRACE_DAYS + 1)
        # The session runs with autoflush off, so the change has to be pushed
        # before the cycle queries for overdue invoices.
        await session.flush()
        await billing_service.run_billing_cycle(session)
        await session.commit()

    resp = await client.get("/api/v1/analytics/dashboard", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "tenant_inactive"


# ---------------------------------------------------------------------------
# Payme
# ---------------------------------------------------------------------------


async def test_payme_rejects_bad_credentials(client: AsyncClient):
    """The only thing between the internet and an endpoint that marks
    invoices paid."""
    resp = await client.post(
        "/api/v1/billing/payme",
        json={"id": 1, "method": "CheckPerformTransaction", "params": {}},
        headers=payme_auth("wrong-key"),
    )
    assert resp.status_code == 200, "Payme retries forever on a non-200"
    assert resp.json()["error"]["code"] == -32504


async def test_payme_requires_authentication(client: AsyncClient):
    resp = await client.post(
        "/api/v1/billing/payme", json={"id": 1, "method": "CheckTransaction", "params": {}}
    )
    assert resp.json()["error"]["code"] == -32504


async def test_payme_full_payment_flow(client: AsyncClient):
    headers, invoice_id, amount = await shop_with_invoice(client)
    tiyin = int(amount * 100)

    check = await client.post(
        "/api/v1/billing/payme",
        json={
            "id": 1,
            "method": "CheckPerformTransaction",
            "params": {"amount": tiyin, "account": {"invoice_id": invoice_id}},
        },
        headers=payme_auth(),
    )
    assert check.json()["result"] == {"allow": True}

    created = await client.post(
        "/api/v1/billing/payme",
        json={
            "id": 2,
            "method": "CreateTransaction",
            "params": {
                "id": "payme-tx-1",
                "time": int(datetime.now(UTC).timestamp() * 1000),
                "amount": tiyin,
                "account": {"invoice_id": invoice_id},
            },
        },
        headers=payme_auth(),
    )
    assert created.json()["result"]["state"] == 1

    performed = await client.post(
        "/api/v1/billing/payme",
        json={"id": 3, "method": "PerformTransaction", "params": {"id": "payme-tx-1"}},
        headers=payme_auth(),
    )
    assert performed.json()["result"]["state"] == 2

    overview = (await client.get("/api/v1/billing", headers=headers)).json()
    assert overview["outstanding"] is None
    assert overview["invoices"][0]["status"] == "paid"
    assert overview["status"] == "active"


async def test_payme_wrong_amount_is_refused(client: AsyncClient):
    """A gateway that could name the amount could name a smaller one."""
    _headers, invoice_id, amount = await shop_with_invoice(client)

    resp = await client.post(
        "/api/v1/billing/payme",
        json={
            "id": 1,
            "method": "CheckPerformTransaction",
            "params": {"amount": 100, "account": {"invoice_id": invoice_id}},
        },
        headers=payme_auth(),
    )
    assert resp.json()["error"]["code"] == -31001


async def test_payme_unknown_invoice_is_refused(client: AsyncClient):
    resp = await client.post(
        "/api/v1/billing/payme",
        json={
            "id": 1,
            "method": "CheckPerformTransaction",
            "params": {
                "amount": 1900,
                "account": {"invoice_id": "00000000-0000-0000-0000-000000000000"},
            },
        },
        headers=payme_auth(),
    )
    assert resp.json()["error"]["code"] == -31050


async def test_payme_repeated_create_returns_the_same_transaction(
    client: AsyncClient,
):
    _headers, invoice_id, amount = await shop_with_invoice(client)
    params = {
        "id": "payme-tx-dup",
        "time": int(datetime.now(UTC).timestamp() * 1000),
        "amount": int(amount * 100),
        "account": {"invoice_id": invoice_id},
    }

    first = await client.post(
        "/api/v1/billing/payme",
        json={"id": 1, "method": "CreateTransaction", "params": params},
        headers=payme_auth(),
    )
    second = await client.post(
        "/api/v1/billing/payme",
        json={"id": 2, "method": "CreateTransaction", "params": params},
        headers=payme_auth(),
    )
    assert first.json()["result"]["transaction"] == second.json()["result"]["transaction"]

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        count = await conn.scalar(text("SELECT count(*) FROM payment_transactions"))
    assert count == 1


async def test_payme_repeated_perform_does_not_bill_twice(client: AsyncClient):
    """Payme retries PerformTransaction; the period must not extend twice."""
    _headers, invoice_id, amount = await shop_with_invoice(client)
    await client.post(
        "/api/v1/billing/payme",
        json={
            "id": 1,
            "method": "CreateTransaction",
            "params": {
                "id": "payme-tx-2",
                "time": int(datetime.now(UTC).timestamp() * 1000),
                "amount": int(amount * 100),
                "account": {"invoice_id": invoice_id},
            },
        },
        headers=payme_auth(),
    )

    async def perform():
        return await client.post(
            "/api/v1/billing/payme",
            json={"id": 2, "method": "PerformTransaction", "params": {"id": "payme-tx-2"}},
            headers=payme_auth(),
        )

    first = await perform()
    async with AsyncSessionLocal() as session, platform_scope(session):
        after_first = (await session.scalar(select(Subscription))).current_period_end

    second = await perform()
    async with AsyncSessionLocal() as session, platform_scope(session):
        after_second = (await session.scalar(select(Subscription))).current_period_end

    assert first.json()["result"]["state"] == second.json()["result"]["state"] == 2
    assert after_first == after_second, "the period was extended twice"


async def test_payme_cancel_after_payment_reopens_the_invoice(client: AsyncClient):
    """The debt is still owed; it just was not collected."""
    _headers, invoice_id, amount = await shop_with_invoice(client)
    await client.post(
        "/api/v1/billing/payme",
        json={
            "id": 1,
            "method": "CreateTransaction",
            "params": {
                "id": "payme-tx-3",
                "time": int(datetime.now(UTC).timestamp() * 1000),
                "amount": int(amount * 100),
                "account": {"invoice_id": invoice_id},
            },
        },
        headers=payme_auth(),
    )
    await client.post(
        "/api/v1/billing/payme",
        json={"id": 2, "method": "PerformTransaction", "params": {"id": "payme-tx-3"}},
        headers=payme_auth(),
    )

    cancelled = await client.post(
        "/api/v1/billing/payme",
        json={
            "id": 3,
            "method": "CancelTransaction",
            "params": {"id": "payme-tx-3", "reason": 5},
        },
        headers=payme_auth(),
    )
    assert cancelled.json()["result"]["state"] == -2

    async with AsyncSessionLocal() as session, platform_scope(session):
        invoice = await session.scalar(select(SubscriptionInvoice))
        subscription = await session.scalar(select(Subscription))
    assert invoice.status is InvoiceStatus.OPEN
    assert invoice.amount_paid == Decimal("0.00")
    assert subscription.status is SubscriptionStatus.PAST_DUE


async def test_payme_check_transaction_echoes_stored_times(client: AsyncClient):
    _headers, invoice_id, amount = await shop_with_invoice(client)
    created_at = int(datetime.now(UTC).timestamp() * 1000)
    await client.post(
        "/api/v1/billing/payme",
        json={
            "id": 1,
            "method": "CreateTransaction",
            "params": {
                "id": "payme-tx-4",
                "time": created_at,
                "amount": int(amount * 100),
                "account": {"invoice_id": invoice_id},
            },
        },
        headers=payme_auth(),
    )
    resp = await client.post(
        "/api/v1/billing/payme",
        json={"id": 2, "method": "CheckTransaction", "params": {"id": "payme-tx-4"}},
        headers=payme_auth(),
    )
    result = resp.json()["result"]
    assert result["create_time"] == created_at
    assert result["state"] == 1


async def test_payme_unknown_method(client: AsyncClient):
    resp = await client.post(
        "/api/v1/billing/payme",
        json={"id": 1, "method": "NoSuchMethod", "params": {}},
        headers=payme_auth(),
    )
    assert resp.json()["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# Click
# ---------------------------------------------------------------------------


async def test_click_rejects_a_bad_signature(client: AsyncClient):
    _headers, invoice_id, amount = await shop_with_invoice(client)
    resp = await client.post(
        "/api/v1/billing/click/prepare",
        data={
            "click_trans_id": "1",
            "service_id": "svc-1",
            "merchant_trans_id": invoice_id,
            "amount": str(amount),
            "action": "0",
            "sign_time": "2026-09-05 12:00:00",
            "sign_string": "deadbeef",
        },
    )
    assert resp.json()["error"] == -1


async def test_click_full_payment_flow(client: AsyncClient):
    headers, invoice_id, amount = await shop_with_invoice(client)

    prepare_payload = {
        "click_trans_id": "click-1",
        "service_id": "svc-1",
        "merchant_trans_id": invoice_id,
        "amount": str(amount),
        "action": "0",
        "sign_time": "2026-09-05 12:00:00",
    }
    prepare_payload["sign_string"] = click_sign(prepare_payload, "0")

    prepared = await client.post("/api/v1/billing/click/prepare", data=prepare_payload)
    body = prepared.json()
    assert body["error"] == 0
    prepare_id = body["merchant_prepare_id"]

    complete_payload = {
        "click_trans_id": "click-1",
        "service_id": "svc-1",
        "merchant_trans_id": invoice_id,
        "merchant_prepare_id": prepare_id,
        "amount": str(amount),
        "action": "1",
        "sign_time": "2026-09-05 12:01:00",
        "error": "0",
    }
    complete_payload["sign_string"] = click_sign(complete_payload, "1")

    completed = await client.post("/api/v1/billing/click/complete", data=complete_payload)
    assert completed.json()["error"] == 0

    overview = (await client.get("/api/v1/billing", headers=headers)).json()
    assert overview["outstanding"] is None
    assert overview["status"] == "active"


async def test_click_wrong_amount_is_refused(client: AsyncClient):
    _headers, invoice_id, _amount = await shop_with_invoice(client)
    payload = {
        "click_trans_id": "click-2",
        "service_id": "svc-1",
        "merchant_trans_id": invoice_id,
        "amount": "1.00",
        "action": "0",
        "sign_time": "2026-09-05 12:00:00",
    }
    payload["sign_string"] = click_sign(payload, "0")

    resp = await client.post("/api/v1/billing/click/prepare", data=payload)
    assert resp.json()["error"] == -2


async def test_click_repeated_complete_does_not_bill_twice(client: AsyncClient):
    _headers, invoice_id, amount = await shop_with_invoice(client)

    prepare_payload = {
        "click_trans_id": "click-3",
        "service_id": "svc-1",
        "merchant_trans_id": invoice_id,
        "amount": str(amount),
        "action": "0",
        "sign_time": "2026-09-05 12:00:00",
    }
    prepare_payload["sign_string"] = click_sign(prepare_payload, "0")
    prepare_id = (await client.post("/api/v1/billing/click/prepare", data=prepare_payload)).json()[
        "merchant_prepare_id"
    ]

    complete_payload = {
        "click_trans_id": "click-3",
        "service_id": "svc-1",
        "merchant_trans_id": invoice_id,
        "merchant_prepare_id": prepare_id,
        "amount": str(amount),
        "action": "1",
        "sign_time": "2026-09-05 12:01:00",
        "error": "0",
    }
    complete_payload["sign_string"] = click_sign(complete_payload, "1")

    first = await client.post("/api/v1/billing/click/complete", data=complete_payload)
    async with AsyncSessionLocal() as session, platform_scope(session):
        after_first = (await session.scalar(select(Subscription))).current_period_end

    second = await client.post("/api/v1/billing/click/complete", data=complete_payload)
    async with AsyncSessionLocal() as session, platform_scope(session):
        after_second = (await session.scalar(select(Subscription))).current_period_end

    assert first.json()["error"] == 0
    assert second.json()["error"] == -4, "a repeat should report already paid"
    assert after_first == after_second


async def test_click_cancellation_leaves_the_invoice_open(client: AsyncClient):
    _headers, invoice_id, amount = await shop_with_invoice(client)

    prepare_payload = {
        "click_trans_id": "click-4",
        "service_id": "svc-1",
        "merchant_trans_id": invoice_id,
        "amount": str(amount),
        "action": "0",
        "sign_time": "2026-09-05 12:00:00",
    }
    prepare_payload["sign_string"] = click_sign(prepare_payload, "0")
    prepare_id = (await client.post("/api/v1/billing/click/prepare", data=prepare_payload)).json()[
        "merchant_prepare_id"
    ]

    complete_payload = {
        "click_trans_id": "click-4",
        "service_id": "svc-1",
        "merchant_trans_id": invoice_id,
        "merchant_prepare_id": prepare_id,
        "amount": str(amount),
        "action": "1",
        "sign_time": "2026-09-05 12:01:00",
        "error": "-5",
    }
    complete_payload["sign_string"] = click_sign(complete_payload, "1")

    resp = await client.post("/api/v1/billing/click/complete", data=complete_payload)
    assert resp.json()["error"] == -9

    async with AsyncSessionLocal() as session, platform_scope(session):
        invoice = await session.scalar(select(SubscriptionInvoice))
    assert invoice.status is InvoiceStatus.OPEN


# ---------------------------------------------------------------------------
# The billing page
# ---------------------------------------------------------------------------


async def test_billing_overview_shows_grace_remaining(client: AsyncClient):
    headers, _invoice_id, _amount = await shop_with_invoice(client)
    overview = (await client.get("/api/v1/billing", headers=headers)).json()

    assert overview["outstanding"] is not None
    assert overview["grace_days_remaining"] is not None
    assert 0 <= overview["grace_days_remaining"] <= settings.BILLING_GRACE_DAYS
    # Both gateways are configured in this test, so both links appear.
    providers = {link["provider"] for link in overview["pay_links"]}
    assert providers == {"payme", "click"}


async def test_unconfigured_gateway_offers_no_button(client: AsyncClient):
    """A dead payment button is worse than none: the shop assumes their card
    failed rather than that nobody wired up the provider."""
    headers, _invoice_id, _amount = await shop_with_invoice(client)
    original = settings.PAYME_MERCHANT_ID
    settings.PAYME_MERCHANT_ID = None
    try:
        overview = (await client.get("/api/v1/billing", headers=headers)).json()
        providers = {link["provider"] for link in overview["pay_links"]}
        assert providers == {"click"}
    finally:
        settings.PAYME_MERCHANT_ID = original


async def test_cashier_cannot_see_billing(client: AsyncClient):
    headers, _invoice_id, _amount = await shop_with_invoice(client)
    await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Sam Cashier",
            "email": "sam@corner.example",
            "password": "another-good-passphrase",
            "role": "cashier",
        },
        headers=headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "sam@corner.example",
            "password": "another-good-passphrase",
            "tenant_slug": "corner",
        },
    )
    cashier = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get("/api/v1/billing", headers=cashier)
    assert resp.status_code == 403
