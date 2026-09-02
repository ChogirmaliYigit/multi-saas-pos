"""Dashboard and reporting queries.

All aggregation happens in Postgres. Pulling rows into Python to sum them
works fine on a demo shop and falls over on a year of trading; these stay as
single grouped queries so the work scales with the index rather than the
result set.

Every query here is automatically scoped by the tenant filter and RLS, so
there is no `WHERE tenant_id` in sight -- adding one would be redundant, and
its absence is not a bug.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Product
from app.models.enums import OrderStatus, ShiftStatus
from app.models.inventory import StockItem
from app.models.sales import Order, OrderItem, Payment, Shift
from app.models.tenant import Branch, Tenant
from app.schemas.analytics import (
    DashboardSummary,
    LowStockItem,
    PaymentBreakdown,
    RevenuePoint,
    SalesByHour,
    TopProduct,
)

ZERO = Decimal("0")
_COMPLETED = Order.status.in_([OrderStatus.COMPLETED, OrderStatus.PARTIALLY_REFUNDED])


def _day_bounds(tenant: Tenant, day: date) -> tuple[datetime, datetime]:
    """A shop's "today" ends when the shop closes, not at UTC midnight.

    Reporting in UTC would split a late-evening trading session across two
    days for anyone west of Greenwich, and the owner would see yesterday's
    takings on today's dashboard.
    """
    try:
        tz = ZoneInfo(tenant.timezone)
    except Exception:
        tz = UTC
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


def _branch_filter(branch_id: uuid.UUID | None):
    return [Order.branch_id == branch_id] if branch_id else []


async def dashboard_summary(
    session: AsyncSession, tenant: Tenant, branch_id: uuid.UUID | None = None
) -> DashboardSummary:
    try:
        tz = ZoneInfo(tenant.timezone)
    except Exception:
        tz = UTC
    today = datetime.now(tz).date()

    today_start, today_end = _day_bounds(tenant, today)
    yest_start, yest_end = _day_bounds(tenant, today - timedelta(days=1))
    month_start, _ = _day_bounds(tenant, today.replace(day=1))

    branch = _branch_filter(branch_id)

    async def totals(start: datetime, end: datetime) -> tuple[Decimal, int, Decimal]:
        row = (
            await session.execute(
                select(
                    func.coalesce(func.sum(Order.total), 0),
                    func.count(Order.id),
                    func.coalesce(func.sum(Order.total - Order.cost_total), 0),
                ).where(
                    _COMPLETED,
                    Order.completed_at >= start,
                    Order.completed_at < end,
                    *branch,
                )
            )
        ).one()
        return Decimal(row[0]), row[1], Decimal(row[2])

    revenue_today, orders_today, margin_today = await totals(today_start, today_end)
    revenue_yesterday, _, _ = await totals(yest_start, yest_end)
    revenue_month, _, _ = await totals(month_start, today_end)

    # Low stock uses the per-branch override when set, else the product's own
    # threshold -- a flagship branch may want a deeper buffer than a kiosk.
    threshold = func.coalesce(StockItem.low_stock_threshold, Product.low_stock_threshold)
    stock_conditions = [
        Product.is_active.is_(True),
        Product.deleted_at.is_(None),
        Product.track_stock.is_(True),
    ]
    if branch_id:
        stock_conditions.append(StockItem.branch_id == branch_id)

    low_stock_count = (
        await session.scalar(
            select(func.count())
            .select_from(StockItem)
            .join(Product, Product.id == StockItem.product_id)
            .where(
                *stock_conditions,
                StockItem.quantity > 0,
                threshold > 0,
                StockItem.quantity <= threshold,
            )
        )
    ) or 0

    out_of_stock_count = (
        await session.scalar(
            select(func.count())
            .select_from(StockItem)
            .join(Product, Product.id == StockItem.product_id)
            .where(*stock_conditions, StockItem.quantity <= 0)
        )
    ) or 0

    active_shifts = (
        await session.scalar(
            select(func.count())
            .select_from(Shift)
            .where(
                Shift.status == ShiftStatus.OPEN,
                *([Shift.branch_id == branch_id] if branch_id else []),
            )
        )
    ) or 0

    return DashboardSummary(
        currency=tenant.currency,
        revenue_today=revenue_today,
        revenue_yesterday=revenue_yesterday,
        orders_today=orders_today,
        average_basket=(revenue_today / orders_today) if orders_today else ZERO,
        gross_margin_today=margin_today,
        revenue_month=revenue_month,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        active_shifts=active_shifts,
    )


async def revenue_series(
    session: AsyncSession,
    tenant: Tenant,
    *,
    days: int = 30,
    branch_id: uuid.UUID | None = None,
) -> list[RevenuePoint]:
    """Daily revenue for the dashboard chart.

    Days with no sales are filled in as zero rather than omitted -- a line
    chart that skips empty days compresses a quiet week and reads as steady
    trading.
    """
    try:
        tz = ZoneInfo(tenant.timezone)
    except Exception:
        tz = UTC
    today = datetime.now(tz).date()
    start, _ = _day_bounds(tenant, today - timedelta(days=days - 1))
    _, end = _day_bounds(tenant, today)

    # Bucket by the shop's local day, not UTC.
    local_day = func.date(func.timezone(tenant.timezone, Order.completed_at))

    rows = (
        await session.execute(
            select(
                local_day.label("day"),
                func.coalesce(func.sum(Order.total), 0),
                func.count(Order.id),
                func.coalesce(func.sum(Order.total - Order.cost_total), 0),
            )
            .where(
                _COMPLETED,
                Order.completed_at >= start,
                Order.completed_at < end,
                *_branch_filter(branch_id),
            )
            .group_by(local_day)
            .order_by(local_day)
        )
    ).all()

    by_day = {row[0]: row for row in rows}
    series: list[RevenuePoint] = []
    for offset in range(days):
        day = today - timedelta(days=days - 1 - offset)
        row = by_day.get(day)
        series.append(
            RevenuePoint(
                day=day,
                revenue=Decimal(row[1]) if row else ZERO,
                orders=row[2] if row else 0,
                margin=Decimal(row[3]) if row else ZERO,
            )
        )
    return series


async def top_products(
    session: AsyncSession,
    tenant: Tenant,
    *,
    days: int = 30,
    limit: int = 10,
    branch_id: uuid.UUID | None = None,
) -> list[TopProduct]:
    try:
        tz = ZoneInfo(tenant.timezone)
    except Exception:
        tz = UTC
    today = datetime.now(tz).date()
    start, _ = _day_bounds(tenant, today - timedelta(days=days - 1))

    rows = (
        await session.execute(
            select(
                OrderItem.product_id,
                # Snapshot name: the product may since have been renamed or
                # deleted, and the report should still say what was sold.
                func.min(OrderItem.product_name),
                func.min(OrderItem.sku),
                func.sum(OrderItem.quantity),
                func.sum(OrderItem.line_total),
                func.sum(OrderItem.line_total - (OrderItem.unit_cost * OrderItem.quantity)),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(_COMPLETED, Order.completed_at >= start, *_branch_filter(branch_id))
            .group_by(OrderItem.product_id)
            .order_by(func.sum(OrderItem.line_total).desc())
            .limit(limit)
        )
    ).all()

    return [
        TopProduct(
            product_id=row[0],
            name=row[1],
            sku=row[2],
            quantity_sold=Decimal(row[3]),
            revenue=Decimal(row[4]),
            margin=Decimal(row[5]),
        )
        for row in rows
    ]


async def low_stock_items(
    session: AsyncSession, *, branch_id: uuid.UUID | None = None, limit: int = 50
) -> list[LowStockItem]:
    threshold = func.coalesce(StockItem.low_stock_threshold, Product.low_stock_threshold)
    conditions = [
        Product.is_active.is_(True),
        Product.deleted_at.is_(None),
        Product.track_stock.is_(True),
        threshold > 0,
        StockItem.quantity <= threshold,
    ]
    if branch_id:
        conditions.append(StockItem.branch_id == branch_id)

    rows = (
        await session.execute(
            select(
                Product.id,
                Product.name,
                Product.sku,
                Branch.id,
                Branch.name,
                StockItem.quantity,
                threshold,
            )
            .select_from(StockItem)
            .join(Product, Product.id == StockItem.product_id)
            .join(Branch, Branch.id == StockItem.branch_id)
            .where(*conditions)
            .order_by(StockItem.quantity)
            .limit(limit)
        )
    ).all()

    return [
        LowStockItem(
            product_id=row[0],
            name=row[1],
            sku=row[2],
            branch_id=row[3],
            branch_name=row[4],
            quantity=Decimal(row[5]),
            threshold=Decimal(row[6]),
        )
        for row in rows
    ]


async def payment_breakdown(
    session: AsyncSession,
    tenant: Tenant,
    *,
    days: int = 30,
    branch_id: uuid.UUID | None = None,
) -> list[PaymentBreakdown]:
    try:
        tz = ZoneInfo(tenant.timezone)
    except Exception:
        tz = UTC
    start, _ = _day_bounds(tenant, datetime.now(tz).date() - timedelta(days=days - 1))

    rows = (
        await session.execute(
            select(
                Payment.method,
                func.coalesce(func.sum(Payment.amount), 0),
                func.count(Payment.id),
            )
            .join(Order, Order.id == Payment.order_id)
            .where(_COMPLETED, Order.completed_at >= start, *_branch_filter(branch_id))
            .group_by(Payment.method)
            .order_by(func.sum(Payment.amount).desc())
        )
    ).all()

    return [
        PaymentBreakdown(method=row[0].value, total=Decimal(row[1]), count=row[2]) for row in rows
    ]


async def sales_by_hour(
    session: AsyncSession,
    tenant: Tenant,
    *,
    days: int = 7,
    branch_id: uuid.UUID | None = None,
) -> list[SalesByHour]:
    """Trading by hour of day -- what staffing decisions get made from."""
    try:
        tz = ZoneInfo(tenant.timezone)
    except Exception:
        tz = UTC
    start, _ = _day_bounds(tenant, datetime.now(tz).date() - timedelta(days=days - 1))

    hour = func.extract("hour", func.timezone(tenant.timezone, Order.completed_at))
    rows = (
        await session.execute(
            select(
                hour.label("hour"),
                func.coalesce(func.sum(Order.total), 0),
                func.count(Order.id),
            )
            .where(_COMPLETED, Order.completed_at >= start, *_branch_filter(branch_id))
            .group_by(hour)
            .order_by(hour)
        )
    ).all()

    by_hour = {int(row[0]): row for row in rows}
    return [
        SalesByHour(
            hour=h,
            revenue=Decimal(by_hour[h][1]) if h in by_hour else ZERO,
            orders=by_hour[h][2] if h in by_hour else 0,
        )
        for h in range(24)
    ]
