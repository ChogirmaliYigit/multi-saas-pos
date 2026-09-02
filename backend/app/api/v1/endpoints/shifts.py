from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import CurrentTenant, CurrentUser, DbSession, require, resolve_branch_id
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.permissions import Permission
from app.models.enums import OrderStatus, PaymentMethod
from app.models.sales import Order, Payment, Shift
from app.schemas.shifts import ShiftCloseIn, ShiftOpenIn, ShiftOut, ShiftSummaryOut
from app.services import order_service

router = APIRouter(prefix="/shifts", tags=["shifts"])


@router.get("/current", response_model=ShiftOut | None)
async def current_shift(
    db: DbSession,
    user: CurrentUser,
    _: Annotated[object, Depends(require(Permission.SHIFT_OPEN))],
) -> Shift | None:
    """What the terminal asks on load, to decide whether to show the till or
    the "open your drawer" screen."""
    branch_id = resolve_branch_id(user, None)
    if branch_id is None:
        return None
    return await order_service.get_open_shift(db, user_id=user.id, branch_id=branch_id)


@router.post("/open", response_model=ShiftOut)
async def open_shift(
    payload: ShiftOpenIn,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
    _: Annotated[object, Depends(require(Permission.SHIFT_OPEN))],
) -> Shift:
    branch_id = resolve_branch_id(user, payload.branch_id)
    if branch_id is None:
        raise PermissionDeniedError("No branch assigned to this terminal.")
    return await order_service.open_shift(
        db,
        tenant_id=tenant.id,
        user=user,
        branch_id=branch_id,
        opening_float=payload.opening_float,
    )


@router.get("/current/summary", response_model=ShiftSummaryOut)
async def current_shift_summary(
    db: DbSession,
    user: CurrentUser,
    _: Annotated[object, Depends(require(Permission.SHIFT_CLOSE))],
) -> ShiftSummaryOut:
    """Takings so far, so the cashier counts against a real figure."""
    branch_id = resolve_branch_id(user, None)
    shift = (
        await order_service.get_open_shift(db, user_id=user.id, branch_id=branch_id)
        if branch_id
        else None
    )
    if shift is None:
        raise NotFoundError("No open shift.", code="no_open_shift")

    totals = (
        await db.execute(
            select(
                func.count(Order.id),
                func.coalesce(func.sum(Order.total), 0),
                func.coalesce(func.sum(Order.refunded_total), 0),
            ).where(Order.shift_id == shift.id, Order.status != OrderStatus.DRAFT)
        )
    ).one()

    by_method = dict(
        (
            await db.execute(
                select(Payment.method, func.coalesce(func.sum(Payment.amount), 0))
                .join(Order, Order.id == Payment.order_id)
                .where(Order.shift_id == shift.id)
                .group_by(Payment.method)
            )
        ).all()
    )

    return ShiftSummaryOut(
        shift=ShiftOut.model_validate(shift),
        order_count=totals[0],
        gross_sales=Decimal(totals[1]),
        cash_sales=Decimal(by_method.get(PaymentMethod.CASH, 0)),
        card_sales=Decimal(by_method.get(PaymentMethod.CARD, 0)),
        refund_total=Decimal(totals[2]),
    )


@router.post("/current/close", response_model=ShiftOut)
async def close_current_shift(
    payload: ShiftCloseIn,
    db: DbSession,
    user: CurrentUser,
    _: Annotated[object, Depends(require(Permission.SHIFT_CLOSE))],
) -> Shift:
    branch_id = resolve_branch_id(user, None)
    shift = (
        await order_service.get_open_shift(db, user_id=user.id, branch_id=branch_id)
        if branch_id
        else None
    )
    if shift is None:
        raise NotFoundError("No open shift.", code="no_open_shift")

    return await order_service.close_shift(
        db, shift=shift, counted_cash=payload.counted_cash, note=payload.note
    )
