"""Checkout.

The one place in the system where money, stock and audit history all change
together. Everything here runs inside the request transaction so a failure
anywhere leaves no partial sale, no phantom stock movement, and no receipt
number burned.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import APIError, ConflictError, NotFoundError
from app.models.catalog import Product
from app.models.enums import (
    DiscountType,
    OrderStatus,
    PaymentStatus,
    ShiftStatus,
    StockMovementType,
)
from app.models.inventory import StockMovement
from app.models.sales import Order, OrderItem, Payment, Shift
from app.models.tenant import Tenant
from app.models.user import User
from app.services.pricing import (
    ZERO,
    CartTotals,
    LineInput,
    calculate_cart,
    money,
    quantity,
)


class InsufficientStockError(APIError):
    status_code = 409
    code = "insufficient_stock"
    message = "Not enough stock to complete this sale."


class NoOpenShiftError(APIError):
    status_code = 409
    code = "no_open_shift"
    message = "Open a shift before taking payment."


class PaymentMismatchError(APIError):
    status_code = 400
    code = "payment_mismatch"
    message = "Payments do not cover the order total."


async def next_order_number(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    branch_code: str,
    tz: str,
) -> str:
    """Atomically reserve the next receipt number for this branch and day.

    A single INSERT ... ON CONFLICT DO UPDATE ... RETURNING makes the database
    the arbiter. Two tills hitting this at the same instant serialise on the
    row lock and get consecutive numbers -- no read-then-write race, and no
    advisory locks to leak.
    """
    try:
        local_now = datetime.now(ZoneInfo(tz))
    except Exception:
        local_now = datetime.now(UTC)
    period = local_now.strftime("%Y%m%d")

    result = await session.execute(
        text(
            """
            INSERT INTO order_counters
                (tenant_id, branch_id, period, last_value, created_at, updated_at)
            VALUES (:tenant_id, :branch_id, :period, 1, now(), now())
            ON CONFLICT (tenant_id, branch_id, period)
            DO UPDATE SET last_value = order_counters.last_value + 1,
                          updated_at = now()
            RETURNING last_value
            """
        ),
        {"tenant_id": tenant_id, "branch_id": branch_id, "period": period},
    )
    sequence = result.scalar_one()
    return f"{branch_code}-{period}-{sequence:04d}"


async def get_open_shift(
    session: AsyncSession, *, user_id: uuid.UUID, branch_id: uuid.UUID
) -> Shift | None:
    return await session.scalar(
        select(Shift).where(
            Shift.user_id == user_id,
            Shift.branch_id == branch_id,
            Shift.status == ShiftStatus.OPEN,
        )
    )


async def _decrement_stock(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    product_id: uuid.UUID,
    qty: Decimal,
    allow_negative: bool,
) -> Decimal:
    """Take stock off the shelf, atomically.

    The guard lives in the WHERE clause, not in a preceding SELECT. Checking
    availability and then updating would let two terminals both pass the check
    and both sell the last unit; here the row lock means exactly one UPDATE
    matches and the loser gets zero rows back.
    """
    condition = "" if allow_negative else "AND (quantity - reserved_quantity) >= :qty"
    result = await session.execute(
        text(
            f"""
            UPDATE stock_items
               SET quantity = quantity - :qty, updated_at = now()
             WHERE tenant_id = :tenant_id
               AND branch_id = :branch_id
               AND product_id = :product_id
               {condition}
         RETURNING quantity
            """
        ),
        {
            "tenant_id": tenant_id,
            "branch_id": branch_id,
            "product_id": product_id,
            "qty": qty,
        },
    )
    row = result.first()
    if row is None:
        raise InsufficientStockError(
            details={"product_id": str(product_id)},
        )
    return Decimal(row[0])


async def create_order(
    session: AsyncSession,
    *,
    tenant: Tenant,
    cashier: User,
    branch_id: uuid.UUID,
    items: list[dict],
    payments: list[dict],
    customer_id: uuid.UUID | None = None,
    order_discount_type: DiscountType = DiscountType.NONE,
    order_discount_value: Decimal = ZERO,
    note: str | None = None,
    idempotency_key: str | None = None,
) -> Order:
    """Turn a cart into a completed sale.

    Prices come from the database, never from the request. A client that sends
    `unit_price: 0.01` gets charged the real shelf price -- the cart payload is
    a list of *what*, not *how much*.
    """
    if idempotency_key:
        existing = await session.scalar(
            select(Order).where(Order.idempotency_key == idempotency_key)
        )
        if existing is not None:
            # A retry from a tablet whose connection dropped after the sale
            # committed. Return the original rather than charging twice.
            return existing

    shift = await get_open_shift(session, user_id=cashier.id, branch_id=branch_id)
    if shift is None:
        raise NoOpenShiftError()

    if not items:
        raise APIError("Cannot complete an empty sale.", code="empty_cart")

    product_ids = [uuid.UUID(str(item["product_id"])) for item in items]
    products = {
        product.id: product
        for product in await session.scalars(
            # tax_rate is eager-loaded: pricing reads it for every line, and a
            # lazy load inside async code raises MissingGreenlet rather than
            # quietly issuing N queries.
            select(Product)
            .options(selectinload(Product.tax_rate))
            .where(Product.id.in_(product_ids), Product.deleted_at.is_(None))
        )
    }

    missing = [str(pid) for pid in product_ids if pid not in products]
    if missing:
        raise NotFoundError(
            "Some items are no longer available.",
            code="product_not_found",
            details={"product_ids": missing},
        )

    lines: list[LineInput] = []
    for item in items:
        product = products[uuid.UUID(str(item["product_id"]))]
        tax_rate = product.tax_rate.rate if product.tax_rate else ZERO
        tax_inclusive = product.tax_rate.is_inclusive if product.tax_rate else False
        lines.append(
            LineInput(
                product_id=str(product.id),
                name=product.name,
                sku=product.sku,
                barcode=product.barcode,
                unit_price=product.price,
                unit_cost=product.cost_price,
                quantity=quantity(item["quantity"]),
                tax_rate=tax_rate,
                tax_inclusive=tax_inclusive,
                discount_type=DiscountType(item.get("discount_type", "NONE").lower())
                if isinstance(item.get("discount_type"), str)
                else item.get("discount_type", DiscountType.NONE),
                discount_value=Decimal(str(item.get("discount_value", "0"))),
            )
        )

    settings_blob = tenant.settings or {}
    cash_rounding = settings_blob.get("cash_rounding")
    totals: CartTotals = calculate_cart(
        lines,
        order_discount_type=order_discount_type,
        order_discount_value=order_discount_value,
        cash_rounding=Decimal(str(cash_rounding)) if cash_rounding else None,
    )

    paid_total = money(sum((Decimal(str(p["amount"])) for p in payments), ZERO))
    if paid_total < totals.total:
        raise PaymentMismatchError(
            f"Order total is {totals.total}, payments cover {paid_total}.",
            details={"total": str(totals.total), "paid": str(paid_total)},
        )

    # Change has two sources and both must land on the receipt:
    #   - cash tendered above the amount applied to the sale (hand back a note)
    #   - amounts that overshoot the total outright
    # Recording only the second is what made a 50.00 tender on a 30.00 sale
    # print with no change line at all.
    def _change_for(payment: dict) -> Decimal:
        amount = money(Decimal(str(payment["amount"])))
        tendered = payment.get("tendered_amount")
        if not tendered:
            return ZERO
        return max(ZERO, money(Decimal(str(tendered))) - amount)

    change_per_payment = [_change_for(payment) for payment in payments]
    change_due = money(sum(change_per_payment, ZERO) + max(ZERO, paid_total - totals.total))

    branch_code = await session.scalar(
        text("SELECT code FROM branches WHERE id = :bid"), {"bid": branch_id}
    )
    order_number = await next_order_number(
        session,
        tenant_id=tenant.id,
        branch_id=branch_id,
        branch_code=branch_code or "POS",
        tz=tenant.timezone,
    )

    now = datetime.now(UTC)

    order = Order(
        tenant_id=tenant.id,
        branch_id=branch_id,
        cashier_id=cashier.id,
        customer_id=customer_id,
        shift_id=shift.id,
        order_number=order_number,
        status=OrderStatus.COMPLETED,
        subtotal=totals.subtotal,
        discount_type=order_discount_type,
        discount_value=order_discount_value,
        discount_total=totals.discount_total,
        tax_total=totals.tax_total,
        rounding_adjustment=totals.rounding_adjustment,
        total=totals.total,
        paid_total=paid_total,
        change_due=change_due,
        cost_total=totals.cost_total,
        currency=tenant.currency,
        note=note,
        completed_at=now,
        idempotency_key=idempotency_key,
    )
    session.add(order)
    await session.flush()

    allow_negative = bool(settings_blob.get("allow_negative_stock", False))

    for computed in totals.lines:
        product = products[uuid.UUID(computed.line.product_id)]
        session.add(
            OrderItem(
                tenant_id=tenant.id,
                order_id=order.id,
                product_id=product.id,
                # Snapshot: the receipt must survive a rename or a price change.
                product_name=product.name,
                sku=product.sku,
                barcode=product.barcode,
                quantity=computed.line.quantity,
                unit_price=computed.line.unit_price,
                unit_cost=computed.line.unit_cost,
                discount_amount=computed.discount_amount,
                tax_rate=computed.line.tax_rate,
                tax_amount=computed.tax_amount,
                tax_inclusive=computed.line.tax_inclusive,
                line_total=computed.net,
            )
        )

        if product.track_stock:
            remaining = await _decrement_stock(
                session,
                tenant_id=tenant.id,
                branch_id=branch_id,
                product_id=product.id,
                qty=computed.line.quantity,
                allow_negative=allow_negative,
            )
            session.add(
                StockMovement(
                    tenant_id=tenant.id,
                    branch_id=branch_id,
                    product_id=product.id,
                    created_by_id=cashier.id,
                    movement_type=StockMovementType.SALE,
                    quantity=-computed.line.quantity,
                    quantity_after=remaining,
                    unit_cost=computed.line.unit_cost,
                    reference_type="order",
                    reference_id=order.id,
                )
            )

    cash_in = ZERO
    for payment, payment_change in zip(payments, change_per_payment, strict=True):
        amount = money(Decimal(str(payment["amount"])))
        method = payment["method"]
        tendered = (
            money(Decimal(str(payment["tendered_amount"])))
            if payment.get("tendered_amount")
            else None
        )
        session.add(
            Payment(
                tenant_id=tenant.id,
                order_id=order.id,
                cashier_id=cashier.id,
                method=method,
                status=PaymentStatus.CAPTURED,
                amount=amount,
                tendered_amount=tendered,
                change_amount=payment_change,
                reference=payment.get("reference"),
                card_last4=payment.get("card_last4"),
                processed_at=now,
            )
        )
        if getattr(method, "value", method) == "cash":
            # What physically entered the drawer, which is the tendered note
            # rather than the amount applied to the sale.
            cash_in += tendered if tendered is not None else amount

    # Keep the drawer's expected balance current so closing the shift can
    # reconcile against counted cash.
    shift.expected_cash = money(shift.expected_cash + cash_in - change_due)

    await session.flush()
    return order


async def load_order(session: AsyncSession, order_id: uuid.UUID) -> Order:
    """Fetch a complete order for the receipt view."""
    from sqlalchemy.orm import selectinload

    order = await session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payments),
            selectinload(Order.customer),
            selectinload(Order.cashier),
            selectinload(Order.branch),
        )
    )
    if order is None:
        raise NotFoundError("Order not found.")
    return order


async def open_shift(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user: User,
    branch_id: uuid.UUID,
    opening_float: Decimal,
) -> Shift:
    existing = await get_open_shift(session, user_id=user.id, branch_id=branch_id)
    if existing is not None:
        raise ConflictError("You already have an open shift.", code="shift_already_open")

    shift = Shift(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user.id,
        opened_at=datetime.now(UTC),
        opening_float=money(opening_float),
        expected_cash=money(opening_float),
    )
    session.add(shift)
    await session.flush()
    return shift


async def close_shift(
    session: AsyncSession, *, shift: Shift, counted_cash: Decimal, note: str | None
) -> Shift:
    shift.counted_cash = money(counted_cash)
    # Positive means the drawer holds more than the system expected.
    shift.cash_difference = money(shift.counted_cash - shift.expected_cash)
    shift.closed_at = datetime.now(UTC)
    shift.status = ShiftStatus.CLOSED
    shift.note = note
    await session.flush()
    return shift
