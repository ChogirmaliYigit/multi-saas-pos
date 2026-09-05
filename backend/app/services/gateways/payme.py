"""Payme merchant API.

The flow is the inverse of a Stripe-style integration: Payme calls us. We
expose one JSON-RPC endpoint and implement the six methods it drives, and
Payme decides when each runs.

Two details cause most of the bugs in Payme integrations, so they are handled
in one place here and nowhere else in the codebase:

  * amounts are in **tiyin**, 1/100 of a som; and
  * times are **milliseconds** since the epoch, not seconds.

Both are converted at this boundary so no other module learns them.

Reference: https://developer.help.paycom.uz/metody-merchant-api/
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import InvoiceStatus, PaymentProvider, TransactionState
from app.models.subscription import PaymentTransaction
from app.services import billing_service

# Payme's own error codes. The negative space is theirs, not ours -- a
# handler that invents a code gets an unhelpful "unknown error" in their
# dashboard rather than the specific message the merchant needs.
ERR_INVALID_AMOUNT = -31001
ERR_TX_NOT_FOUND = -31003
ERR_CANNOT_PERFORM = -31008
ERR_CANNOT_CANCEL = -31007
ERR_INVALID_ACCOUNT = -31050
ERR_UNAUTHORIZED = -32504
ERR_METHOD_NOT_FOUND = -32601
ERR_PARSE = -32700

# Payme's transaction states, which are not ours.
PAYME_CREATED = 1
PAYME_PERFORMED = 2
PAYME_CANCELLED_BEFORE = -1
PAYME_CANCELLED_AFTER = -2

# A transaction Payme created but never performed expires after 12 hours.
TRANSACTION_TIMEOUT_MS = 12 * 60 * 60 * 1000


class PaymeError(Exception):
    """Carries a Payme error code and the localised message they display."""

    def __init__(self, code: int, message: str, data: str | None = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def to_tiyin(amount: Decimal) -> int:
    return int(amount * 100)


def from_tiyin(amount: int) -> Decimal:
    return (Decimal(amount) / 100).quantize(Decimal("0.01"))


def check_auth(authorization: str | None) -> None:
    """Payme authenticates as Basic "Paycom:<key>".

    The key is a shared secret they send to us, so this is the only thing
    standing between the internet and an endpoint that marks invoices paid.
    """
    if not settings.payme_configured:
        raise PaymeError(ERR_UNAUTHORIZED, "Payme is not configured.")

    if not authorization or not authorization.lower().startswith("basic "):
        raise PaymeError(ERR_UNAUTHORIZED, "Missing credentials.")

    try:
        decoded = base64.b64decode(authorization.split(" ", 1)[1]).decode()
        login, _, key = decoded.partition(":")
    except Exception as exc:
        raise PaymeError(ERR_UNAUTHORIZED, "Malformed credentials.") from exc

    # The test key is accepted alongside the live one so a sandbox merchant
    # can be exercised without a second deployment.
    valid = {settings.PAYME_KEY}
    if settings.PAYME_TEST_KEY:
        valid.add(settings.PAYME_TEST_KEY)

    if login != "Paycom" or key not in valid:
        raise PaymeError(ERR_UNAUTHORIZED, "Invalid credentials.")


def _localised(message: str) -> dict[str, str]:
    """Payme shows the message in the payer's language; all three are
    required, so an untranslated string is repeated rather than omitted."""
    return {"ru": message, "uz": message, "en": message}


async def _resolve_invoice(session: AsyncSession, params: dict) -> Any:
    account = params.get("account") or {}
    raw = account.get("invoice_id") or account.get("order_id")
    if not raw:
        raise PaymeError(ERR_INVALID_ACCOUNT, "Invoice reference is missing.", data="invoice_id")

    import uuid as _uuid

    try:
        invoice_id = _uuid.UUID(str(raw))
    except ValueError as exc:
        raise PaymeError(ERR_INVALID_ACCOUNT, "Invoice not found.", data="invoice_id") from exc

    invoice = await billing_service.find_invoice(session, invoice_id)
    if invoice is None:
        raise PaymeError(ERR_INVALID_ACCOUNT, "Invoice not found.", data="invoice_id")
    return invoice


async def check_perform_transaction(session: AsyncSession, params: dict) -> dict:
    """Payme asks whether it may show a payment form for this account."""
    invoice = await _resolve_invoice(session, params)
    amount = from_tiyin(int(params.get("amount", 0)))

    if invoice.status is InvoiceStatus.PAID:
        raise PaymeError(ERR_CANNOT_PERFORM, "This invoice is already paid.")
    if invoice.status in (InvoiceStatus.VOID, InvoiceStatus.UNCOLLECTIBLE):
        raise PaymeError(ERR_CANNOT_PERFORM, "This invoice was cancelled.")
    if amount != invoice.amount_due:
        raise PaymeError(ERR_INVALID_AMOUNT, "Incorrect amount.")

    return {"allow": True}


async def create_transaction(session: AsyncSession, params: dict) -> dict:
    """Payme is holding funds and asks us to record the attempt.

    Called repeatedly with the same id -- a repeat must return the original
    row, never create a second one.
    """
    transaction_id = str(params["id"])
    amount = from_tiyin(int(params.get("amount", 0)))
    payme_time = int(params.get("time", _now_ms()))

    existing = await billing_service.find_transaction(
        session, provider=PaymentProvider.PAYME, external_id=transaction_id
    )
    if existing is not None:
        if existing.state is not TransactionState.CREATED:
            raise PaymeError(ERR_CANNOT_PERFORM, "This transaction is no longer open.")
        if _now_ms() - (existing.created_time or 0) > TRANSACTION_TIMEOUT_MS:
            # Payme requires us to expire our own stale transactions; if we
            # do not, their reconciliation flags a permanent mismatch.
            existing.state = TransactionState.CANCELLED
            existing.cancelled_time = _now_ms()
            existing.cancel_reason = 4
            await session.flush()
            raise PaymeError(ERR_CANNOT_PERFORM, "This transaction has expired.")
        return {
            "create_time": existing.created_time,
            "transaction": str(existing.id),
            "state": PAYME_CREATED,
        }

    invoice = await _resolve_invoice(session, params)
    if invoice.status is InvoiceStatus.PAID:
        raise PaymeError(ERR_CANNOT_PERFORM, "This invoice is already paid.")
    if amount != invoice.amount_due:
        raise PaymeError(ERR_INVALID_AMOUNT, "Incorrect amount.")

    transaction = await billing_service.record_transaction(
        session,
        invoice=invoice,
        provider=PaymentProvider.PAYME,
        external_id=transaction_id,
        amount=amount,
        created_time=payme_time,
        payload=params,
    )
    return {
        "create_time": transaction.created_time,
        "transaction": str(transaction.id),
        "state": PAYME_CREATED,
    }


async def perform_transaction(session: AsyncSession, params: dict) -> dict:
    """Funds captured. Settle the invoice."""
    transaction = await billing_service.find_transaction(
        session, provider=PaymentProvider.PAYME, external_id=str(params["id"])
    )
    if transaction is None:
        raise PaymeError(ERR_TX_NOT_FOUND, "Transaction not found.")

    if transaction.state is TransactionState.PERFORMED:
        # Payme retries this; the second call must look like the first.
        return {
            "transaction": str(transaction.id),
            "perform_time": transaction.performed_time,
            "state": PAYME_PERFORMED,
        }

    if transaction.state is not TransactionState.CREATED:
        raise PaymeError(ERR_CANNOT_PERFORM, "This transaction was cancelled.")

    if _now_ms() - (transaction.created_time or 0) > TRANSACTION_TIMEOUT_MS:
        transaction.state = TransactionState.CANCELLED
        transaction.cancelled_time = _now_ms()
        transaction.cancel_reason = 4
        await session.flush()
        raise PaymeError(ERR_CANNOT_PERFORM, "This transaction has expired.")

    transaction.state = TransactionState.PERFORMED
    transaction.performed_time = _now_ms()
    await billing_service.mark_paid(session, transaction)

    return {
        "transaction": str(transaction.id),
        "perform_time": transaction.performed_time,
        "state": PAYME_PERFORMED,
    }


async def cancel_transaction(session: AsyncSession, params: dict) -> dict:
    """Cancelled before or after capture -- the state tells us which."""
    transaction = await billing_service.find_transaction(
        session, provider=PaymentProvider.PAYME, external_id=str(params["id"])
    )
    if transaction is None:
        raise PaymeError(ERR_TX_NOT_FOUND, "Transaction not found.")

    reason = params.get("reason")

    if transaction.state is TransactionState.CREATED:
        transaction.state = TransactionState.CANCELLED
        transaction.cancelled_time = _now_ms()
        transaction.cancel_reason = reason
        await session.flush()
        state = PAYME_CANCELLED_BEFORE

    elif transaction.state is TransactionState.PERFORMED:
        transaction.state = TransactionState.REFUNDED
        transaction.cancelled_time = _now_ms()
        transaction.cancel_reason = reason
        await billing_service.mark_refunded(session, transaction)
        state = PAYME_CANCELLED_AFTER

    else:
        # Already cancelled. Report the terminal state rather than erroring;
        # Payme replays cancellations during reconciliation.
        state = (
            PAYME_CANCELLED_AFTER
            if transaction.state is TransactionState.REFUNDED
            else PAYME_CANCELLED_BEFORE
        )

    return {
        "transaction": str(transaction.id),
        "cancel_time": transaction.cancelled_time,
        "state": state,
    }


async def check_transaction(session: AsyncSession, params: dict) -> dict:
    """Status poll. Every timestamp must be echoed exactly as stored, which
    is why the provider's own clock values are kept rather than re-derived."""
    transaction = await billing_service.find_transaction(
        session, provider=PaymentProvider.PAYME, external_id=str(params["id"])
    )
    if transaction is None:
        raise PaymeError(ERR_TX_NOT_FOUND, "Transaction not found.")

    state = {
        TransactionState.CREATED: PAYME_CREATED,
        TransactionState.PERFORMED: PAYME_PERFORMED,
        TransactionState.CANCELLED: PAYME_CANCELLED_BEFORE,
        TransactionState.REFUNDED: PAYME_CANCELLED_AFTER,
    }[transaction.state]

    return {
        "create_time": transaction.created_time or 0,
        "perform_time": transaction.performed_time or 0,
        "cancel_time": transaction.cancelled_time or 0,
        "transaction": str(transaction.id),
        "state": state,
        "reason": transaction.cancel_reason,
    }


async def get_statement(session: AsyncSession, params: dict) -> dict:
    """Payme's reconciliation: every transaction in a window."""
    from sqlalchemy import select

    from app.db.tenant_filter import SKIP_TENANT_FILTER

    start = int(params.get("from", 0))
    end = int(params.get("to", _now_ms()))

    rows = await session.scalars(
        select(PaymentTransaction)
        .where(
            PaymentTransaction.provider == PaymentProvider.PAYME,
            PaymentTransaction.created_time >= start,
            PaymentTransaction.created_time <= end,
        )
        .execution_options(**{SKIP_TENANT_FILTER: True})
    )

    return {
        "transactions": [
            {
                "id": row.external_id,
                "time": row.created_time,
                "amount": to_tiyin(row.amount),
                "account": {"invoice_id": str(row.invoice_id)},
                "create_time": row.created_time or 0,
                "perform_time": row.performed_time or 0,
                "cancel_time": row.cancelled_time or 0,
                "transaction": str(row.id),
                "state": {
                    TransactionState.CREATED: PAYME_CREATED,
                    TransactionState.PERFORMED: PAYME_PERFORMED,
                    TransactionState.CANCELLED: PAYME_CANCELLED_BEFORE,
                    TransactionState.REFUNDED: PAYME_CANCELLED_AFTER,
                }[row.state],
                "reason": row.cancel_reason,
            }
            for row in rows
        ]
    }


METHODS = {
    "CheckPerformTransaction": check_perform_transaction,
    "CreateTransaction": create_transaction,
    "PerformTransaction": perform_transaction,
    "CancelTransaction": cancel_transaction,
    "CheckTransaction": check_transaction,
    "GetStatement": get_statement,
}


async def dispatch(session: AsyncSession, body: dict, authorization: str | None) -> dict:
    """One JSON-RPC entry point.

    Always answers 200 with a JSON-RPC envelope, including for errors: Payme
    treats a non-200 as a transport failure and retries indefinitely, which
    turns a permanent rejection into a loop.
    """
    request_id = body.get("id")
    try:
        check_auth(authorization)

        method = body.get("method")
        handler = METHODS.get(method)
        if handler is None:
            raise PaymeError(ERR_METHOD_NOT_FOUND, f"Unknown method {method!r}.")

        result = await handler(session, body.get("params") or {})
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    except PaymeError as exc:
        error: dict[str, Any] = {"code": exc.code, "message": _localised(exc.message)}
        if exc.data:
            error["data"] = exc.data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    except (KeyError, TypeError, ValueError):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": ERR_PARSE, "message": _localised("Malformed request.")},
        }


def checkout_url(invoice_id: str, amount: Decimal, return_url: str | None = None) -> str:
    """The link a shop opens to pay.

    Payme takes its parameters base64-encoded in the path, not as a query
    string.
    """
    parts = [
        f"m={settings.PAYME_MERCHANT_ID}",
        f"ac.invoice_id={invoice_id}",
        f"a={to_tiyin(amount)}",
    ]
    if return_url:
        parts.append(f"c={return_url}")
    encoded = base64.b64encode(";".join(parts).encode()).decode()
    return f"{settings.PAYME_CHECKOUT_URL}/{encoded}"
