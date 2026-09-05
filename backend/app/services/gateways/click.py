"""Click merchant API.

Two form-encoded callbacks rather than Payme's JSON-RPC: Prepare, then
Complete. Click authenticates each with an MD5 signature over a fixed field
order.

MD5 is Click's choice, not ours. It is not being used as a password hash --
it authenticates a message using a shared secret, and the field order is
fixed by their spec, so it is compared in constant time and otherwise left
alone.

Amounts are in som with decimals, unlike Payme's tiyin.

Reference: https://docs.click.uz/click-api-request/
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import InvoiceStatus, PaymentProvider, TransactionState
from app.services import billing_service

# Click's error codes.
OK = 0
ERR_SIGN_CHECK = -1
ERR_INVALID_AMOUNT = -2
ERR_ACTION_NOT_FOUND = -3
ERR_ALREADY_PAID = -4
ERR_USER_NOT_FOUND = -5
ERR_TX_NOT_FOUND = -6
ERR_FAILED_UPDATE = -7
ERR_BAD_REQUEST = -8
ERR_TX_CANCELLED = -9

ACTION_PREPARE = "0"
ACTION_COMPLETE = "1"


def _fail(code: int, note: str) -> dict:
    return {"error": code, "error_note": note}


def verify_signature(payload: dict, action: str) -> bool:
    """MD5 over Click's fixed field order.

    Prepare and Complete sign different field sets -- Complete includes
    merchant_prepare_id -- and getting the order wrong produces a signature
    that never matches, with no hint as to why.
    """
    if not settings.click_configured:
        return False

    secret = settings.CLICK_SECRET_KEY or ""
    if action == ACTION_PREPARE:
        raw = (
            f"{payload.get('click_trans_id', '')}"
            f"{payload.get('service_id', '')}"
            f"{secret}"
            f"{payload.get('merchant_trans_id', '')}"
            f"{payload.get('amount', '')}"
            f"{payload.get('action', '')}"
            f"{payload.get('sign_time', '')}"
        )
    else:
        raw = (
            f"{payload.get('click_trans_id', '')}"
            f"{payload.get('service_id', '')}"
            f"{secret}"
            f"{payload.get('merchant_trans_id', '')}"
            f"{payload.get('merchant_prepare_id', '')}"
            f"{payload.get('amount', '')}"
            f"{payload.get('action', '')}"
            f"{payload.get('sign_time', '')}"
        )

    expected = hashlib.md5(raw.encode()).hexdigest()  # noqa: S324 - Click's spec
    # Constant time: a signature check that short-circuits leaks how much of
    # a guess was right.
    return hmac.compare_digest(expected, str(payload.get("sign_string", "")))


async def _load_invoice(session: AsyncSession, raw_id: str):
    try:
        invoice_id = uuid.UUID(str(raw_id))
    except (ValueError, AttributeError):
        return None
    return await billing_service.find_invoice(session, invoice_id)


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return None


async def prepare(session: AsyncSession, payload: dict) -> dict:
    """Click asks whether this payment may proceed."""
    if not verify_signature(payload, ACTION_PREPARE):
        return _fail(ERR_SIGN_CHECK, "SIGN CHECK FAILED")

    invoice = await _load_invoice(session, payload.get("merchant_trans_id"))
    if invoice is None:
        return _fail(ERR_USER_NOT_FOUND, "Invoice not found")

    amount = _parse_amount(payload.get("amount"))
    if amount is None or amount != invoice.amount_due:
        return _fail(ERR_INVALID_AMOUNT, "Incorrect parameter amount")

    if invoice.status is InvoiceStatus.PAID:
        return _fail(ERR_ALREADY_PAID, "Already paid")
    if invoice.status in (InvoiceStatus.VOID, InvoiceStatus.UNCOLLECTIBLE):
        return _fail(ERR_USER_NOT_FOUND, "Invoice cancelled")

    transaction = await billing_service.record_transaction(
        session,
        invoice=invoice,
        provider=PaymentProvider.CLICK,
        external_id=str(payload.get("click_trans_id")),
        amount=amount,
        payload=payload,
    )

    return {
        "click_trans_id": payload.get("click_trans_id"),
        "merchant_trans_id": str(invoice.id),
        # Click echoes this back in Complete; it is how the two calls are
        # tied together.
        "merchant_prepare_id": str(transaction.id),
        "error": OK,
        "error_note": "Success",
    }


async def complete(session: AsyncSession, payload: dict) -> dict:
    """Funds captured, or the payment was cancelled."""
    if not verify_signature(payload, ACTION_COMPLETE):
        return _fail(ERR_SIGN_CHECK, "SIGN CHECK FAILED")

    transaction = await billing_service.find_transaction(
        session,
        provider=PaymentProvider.CLICK,
        external_id=str(payload.get("click_trans_id")),
    )
    if transaction is None:
        return _fail(ERR_TX_NOT_FOUND, "Transaction does not exist")

    # A negative error from Click means the payer cancelled or it failed on
    # their side. Nothing was captured, so nothing is settled.
    try:
        click_error = int(payload.get("error", 0))
    except (TypeError, ValueError):
        click_error = 0

    if click_error < 0:
        if transaction.state is TransactionState.CREATED:
            transaction.state = TransactionState.CANCELLED
            transaction.cancel_reason = click_error
            await session.flush()
        return {
            "click_trans_id": payload.get("click_trans_id"),
            "merchant_trans_id": str(transaction.invoice_id),
            "merchant_confirm_id": str(transaction.id),
            "error": ERR_TX_CANCELLED,
            "error_note": "Transaction cancelled",
        }

    if transaction.state is TransactionState.PERFORMED:
        # Click retries; a repeat must not bill or extend anything twice.
        return {
            "click_trans_id": payload.get("click_trans_id"),
            "merchant_trans_id": str(transaction.invoice_id),
            "merchant_confirm_id": str(transaction.id),
            "error": ERR_ALREADY_PAID,
            "error_note": "Already paid",
        }

    if transaction.state is not TransactionState.CREATED:
        return _fail(ERR_TX_CANCELLED, "Transaction cancelled")

    amount = _parse_amount(payload.get("amount"))
    if amount is None or amount != transaction.amount:
        return _fail(ERR_INVALID_AMOUNT, "Incorrect parameter amount")

    transaction.state = TransactionState.PERFORMED
    await billing_service.mark_paid(session, transaction)

    return {
        "click_trans_id": payload.get("click_trans_id"),
        "merchant_trans_id": str(transaction.invoice_id),
        "merchant_confirm_id": str(transaction.id),
        "error": OK,
        "error_note": "Success",
    }


def checkout_url(invoice_id: str, amount: Decimal, return_url: str | None = None) -> str:
    """A plain query string, unlike Payme's base64 path."""
    url = (
        f"{settings.CLICK_CHECKOUT_URL}"
        f"?service_id={settings.CLICK_SERVICE_ID}"
        f"&merchant_id={settings.CLICK_MERCHANT_ID}"
        f"&amount={amount}"
        f"&transaction_param={invoice_id}"
    )
    if return_url:
        url += f"&return_url={return_url}"
    return url
