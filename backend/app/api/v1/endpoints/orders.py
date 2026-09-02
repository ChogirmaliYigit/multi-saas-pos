from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentTenant,
    CurrentUser,
    DbSession,
    require,
    require_active_subscription,
    resolve_branch_id,
)
from app.core.exceptions import PermissionDeniedError
from app.core.permissions import Permission, permissions_for
from app.models.enums import DiscountType, OrderStatus
from app.models.sales import Order
from app.schemas.common import Page
from app.schemas.orders import OrderCreate, OrderOut, ReceiptOut, ReceiptShop
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_active_subscription)],
)
async def create_order(
    payload: OrderCreate,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
    _: Annotated[object, Depends(require(Permission.ORDER_CREATE))],
) -> Order:
    """Take payment.

    Everything in here -- order, lines, stock decrements, movement ledger,
    payments, drawer balance -- commits as one transaction or not at all.
    """
    branch_id = resolve_branch_id(user, payload.branch_id)
    if branch_id is None:
        raise PermissionDeniedError("No branch assigned to this terminal.")

    # Applying a discount is a separate permission from ringing up a sale:
    # it is the most common way for shrinkage to leave through the front door.
    if payload.discount_type is not DiscountType.NONE or any(
        item.discount_type is not DiscountType.NONE for item in payload.items
    ):
        granted = permissions_for(user.role, user.permission_overrides)
        if Permission.ORDER_DISCOUNT not in granted:
            raise PermissionDeniedError(
                "You may not apply discounts.",
                details={"required": [Permission.ORDER_DISCOUNT]},
            )

    order = await order_service.create_order(
        db,
        tenant=tenant,
        cashier=user,
        branch_id=branch_id,
        items=[item.model_dump() for item in payload.items],
        payments=[payment.model_dump() for payment in payload.payments],
        customer_id=payload.customer_id,
        order_discount_type=payload.discount_type,
        order_discount_value=payload.discount_value,
        note=payload.note,
        idempotency_key=payload.idempotency_key,
    )
    return await order_service.load_order(db, order.id)


@router.get("", response_model=Page[OrderOut])
async def list_orders(
    db: DbSession,
    user: CurrentUser,
    _: Annotated[object, Depends(require(Permission.ORDER_READ))],
    branch_id: uuid.UUID | None = None,
    shift_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
) -> Page[OrderOut]:
    conditions = [Order.status != OrderStatus.DRAFT]

    granted = permissions_for(user.role, user.permission_overrides)
    if Permission.ORDER_READ_ALL not in granted:
        # A cashier sees their own sales, not the whole shop's takings.
        conditions.append(Order.cashier_id == user.id)

    effective_branch = resolve_branch_id(user, branch_id)
    if effective_branch:
        conditions.append(Order.branch_id == effective_branch)
    if shift_id:
        conditions.append(Order.shift_id == shift_id)

    total = await db.scalar(select(func.count()).select_from(Order).where(*conditions))
    rows = await db.scalars(
        select(Order)
        .where(*conditions)
        .options(selectinload(Order.items), selectinload(Order.payments))
        .order_by(Order.completed_at.desc().nullslast(), Order.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return Page[OrderOut](
        items=[OrderOut.model_validate(order) for order in rows],
        total=total or 0,
        page=page,
        size=size,
    )


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID,
    db: DbSession,
    _: Annotated[object, Depends(require(Permission.ORDER_READ))],
) -> Order:
    return await order_service.load_order(db, order_id)


@router.get("/{order_id}/receipt", response_model=ReceiptOut)
async def get_receipt(
    order_id: uuid.UUID,
    db: DbSession,
    tenant: CurrentTenant,
    _: Annotated[object, Depends(require(Permission.ORDER_READ))],
) -> ReceiptOut:
    """One payload for both renderers.

    The ESC/POS byte stream and the PDF are built from this same object, so a
    reprint can never disagree with the paper the customer walked out with.
    """
    order = await order_service.load_order(db, order_id)

    return ReceiptOut(
        order=OrderOut.model_validate(order),
        shop=ReceiptShop(
            name=tenant.name,
            branch_name=order.branch.name if order.branch else tenant.name,
            address=tenant.address,
            phone=tenant.phone,
            tax_number=tenant.tax_number,
            header=tenant.receipt_header,
            footer=tenant.receipt_footer,
            currency=order.currency,
            locale=tenant.locale,
        ),
        cashier_name=order.cashier.full_name if order.cashier else None,
        customer_name=order.customer.name if order.customer else None,
        printed_at=datetime.now(UTC),
    )
