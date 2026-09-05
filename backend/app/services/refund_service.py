"""Refunds.

The mirror of checkout, and the same rules apply: money and stock move
together or not at all, and every figure is recomputed from the order rather
than taken from the request. A client that could name its own refund amount
would be a cash-withdrawal endpoint.

Refunds are never destructive. The original order keeps its totals; what
changes is `refunded_total` on the order, `refunded_quantity` on each line,
and a new Refund row. A receipt reprinted afterwards still shows what the
customer originally paid, with the refund recorded against it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import APIError, NotFoundError
from app.models.enums import (
    OrderStatus,
    PaymentMethod,
    StockMovementType,
)
from app.models.inventory import StockMovement
from app.models.sales import Order, OrderItem, Refund
from app.models.tenant import Tenant
from app.models.user import User
from app.services.order_service import NoOpenShiftError, get_open_shift
from app.services.pricing import ZERO, money, quantity

_SETTLED = (OrderStatus.COMPLETED, OrderStatus.PARTIALLY_REFUNDED)


class OrderNotRefundableError(APIError):
    status_code = 409
    code = "order_not_refundable"
    message = "This order cannot be refunded."


class RefundExceedsOrderError(APIError):
    status_code = 400
    code = "refund_exceeds_order"
    message = "That is more than remains on this order."


async def load_for_refund(session: AsyncSession, order_id: uuid.UUID) -> Order:
    order = await session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payments),
            selectinload(Order.refunds),
        )
    )
    if order is None:
        raise NotFoundError("Order not found.")
    return order


def _line_refund_amounts(item: OrderItem, refund_qty: Decimal) -> tuple[Decimal, Decimal]:
    """The share of a line's net and tax attributable to `refund_qty`.

    `line_total` is already net of the line discount and of this line's slice
    of any order-level discount, so a proportional share is the correct
    figure: refunding half a discounted line returns half of what the customer
    actually paid for it, not half the list price.
    """
    if item.quantity <= ZERO:
        return ZERO, ZERO
    share = refund_qty / item.quantity
    return money(item.line_total * share), money(item.tax_amount * share)


async def refund_order(
    session: AsyncSession,
    *,
    tenant: Tenant,
    actor: User,
    order: Order,
    lines: list[dict],
    method: PaymentMethod | None = None,
    reason: str | None = None,
    restock: bool = True,
    idempotency_key: str | None = None,
) -> Refund:
    """Refund whole lines or part of them.

    `lines` is [{"order_item_id": ..., "quantity": ...}]. An empty list means
    "everything still refundable".
    """
    if idempotency_key:
        existing = await session.scalar(
            select(Refund).where(
                Refund.order_id == order.id,
                Refund.line_items.op("->>")("idempotency_key") == idempotency_key,
            )
        )
        if existing is not None:
            return existing

    if order.status not in _SETTLED:
        raise OrderNotRefundableError(f"Order {order.order_number} is {order.status.value}.")

    # Money leaving the till has to land in a shift, or the drawer count at
    # close cannot be reconciled.
    shift = await get_open_shift(session, user_id=actor.id, branch_id=order.branch_id)
    if shift is None:
        raise NoOpenShiftError("Open a shift before refunding.")

    items_by_id = {item.id: item for item in order.items}

    # No lines given means refund whatever is left.
    if not lines:
        lines = [
            {
                "order_item_id": str(item.id),
                "quantity": str(item.quantity - item.refunded_quantity),
            }
            for item in order.items
            if item.quantity - item.refunded_quantity > ZERO
        ]
    if not lines:
        raise RefundExceedsOrderError("Nothing left to refund on this order.")

    total = ZERO
    tax_total = ZERO
    recorded: list[dict] = []
    movements: list[tuple[uuid.UUID, Decimal, Decimal]] = []

    for entry in lines:
        item_id = uuid.UUID(str(entry["order_item_id"]))
        item = items_by_id.get(item_id)
        if item is None:
            raise NotFoundError("That line is not part of this order.", code="line_not_found")

        refund_qty = quantity(entry["quantity"])
        if refund_qty <= ZERO:
            continue

        remaining = item.quantity - item.refunded_quantity
        if refund_qty > remaining:
            raise RefundExceedsOrderError(
                f"{item.product_name}: {remaining} left to refund, asked for {refund_qty}.",
                details={
                    "order_item_id": str(item_id),
                    "remaining": str(remaining),
                    "requested": str(refund_qty),
                },
            )

        amount, tax = _line_refund_amounts(item, refund_qty)
        total += amount
        tax_total += tax

        item.refunded_quantity = item.refunded_quantity + refund_qty
        recorded.append(
            {
                "order_item_id": str(item_id),
                "product_name": item.product_name,
                "quantity": str(refund_qty),
                "amount": str(amount),
                "tax_amount": str(tax),
            }
        )
        if item.product_id is not None:
            movements.append((item.product_id, refund_qty, item.unit_cost))

    total = money(total)
    if total <= ZERO:
        raise RefundExceedsOrderError("Nothing to refund.")

    # Belt and braces against rounding drift across many partial refunds.
    refundable = money(order.total - order.refunded_total)
    if total > refundable:
        total = refundable

    if method is None:
        # Default to how they actually paid; refunding cash for a card sale is
        # how a till ends up short.
        method = (
            max(order.payments, key=lambda p: p.amount).method
            if order.payments
            else PaymentMethod.CASH
        )

    refund = Refund(
        tenant_id=tenant.id,
        order_id=order.id,
        created_by_id=actor.id,
        shift_id=shift.id,
        amount=total,
        method=method,
        reason=reason,
        restocked=restock,
        line_items=(
            {"lines": recorded, "idempotency_key": idempotency_key}
            if idempotency_key
            else {"lines": recorded}
        ),
    )
    session.add(refund)

    order.refunded_total = money(order.refunded_total + total)
    fully = all(item.refunded_quantity >= item.quantity for item in order.items)
    order.status = OrderStatus.REFUNDED if fully else OrderStatus.PARTIALLY_REFUNDED

    if restock:
        for product_id, qty, unit_cost in movements:
            row = (
                await session.execute(
                    text(
                        """
                        UPDATE stock_items
                           SET quantity = quantity + :qty, updated_at = now()
                         WHERE tenant_id = :tenant_id
                           AND branch_id = :branch_id
                           AND product_id = :product_id
                     RETURNING quantity
                        """
                    ),
                    {
                        "qty": qty,
                        "tenant_id": tenant.id,
                        "branch_id": order.branch_id,
                        "product_id": product_id,
                    },
                )
            ).first()
            if row is None:
                # The product was deleted, or never stocked at this branch.
                # The money still goes back; only the ledger entry is skipped.
                continue
            session.add(
                StockMovement(
                    tenant_id=tenant.id,
                    branch_id=order.branch_id,
                    product_id=product_id,
                    created_by_id=actor.id,
                    movement_type=StockMovementType.RETURN,
                    quantity=qty,
                    quantity_after=Decimal(row[0]),
                    unit_cost=unit_cost,
                    reference_type="refund",
                    reference_id=order.id,
                    note=reason,
                )
            )

    if method is PaymentMethod.CASH:
        # Cash out of the drawer, so the expected count at close drops too.
        shift.expected_cash = money(shift.expected_cash - total)
        shift.cash_out = money(shift.cash_out + total)

    await session.flush()
    return refund
