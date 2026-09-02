"""Report generation: CSV and PDF.

Runs in a Celery worker, not in the request. The aggregations mirror the ones
behind the dashboard, so a report and the screen it was exported from cannot
disagree.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.catalog import Product
from app.models.enums import OrderStatus, ReportFormat, ReportType
from app.models.inventory import StockItem
from app.models.sales import Order, OrderItem
from app.models.tenant import Branch, Tenant
from app.models.user import User

_SOLD = Order.status.in_([OrderStatus.COMPLETED, OrderStatus.PARTIALLY_REFUNDED])


def _d(value: Any) -> Decimal:
    """A quantity: three decimals, because weighed goods sell in grams."""
    return Decimal(str(value or 0)).quantize(Decimal("0.001"))


def _m(value: Any) -> Decimal:
    """A money column: always exactly two decimals.

    Postgres returns NUMERIC(14,3) * NUMERIC(14,2) as five decimal places, and
    coalesce(sum(...), 0) as a bare 0 -- so an unquantized report prints
    "17.60000" next to "20.00" and "0" next to "0.00". On a financial export
    that reads as a broken system, whatever the arithmetic underneath.
    """
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------
# Row builders. Each returns (title, headers, rows) so CSV and PDF render the
# exact same data and differ only in how it is drawn.
# --------------------------------------------------------------------------


def _sales_summary(session, tenant, start, end, branch_id):
    local_day = func.date(func.timezone(tenant.timezone, Order.completed_at))
    conditions = [_SOLD, Order.completed_at >= start, Order.completed_at < end]
    if branch_id:
        conditions.append(Order.branch_id == branch_id)

    rows = session.execute(
        select(
            local_day,
            func.count(Order.id),
            func.coalesce(func.sum(Order.subtotal), 0),
            func.coalesce(func.sum(Order.discount_total), 0),
            func.coalesce(func.sum(Order.tax_total), 0),
            func.coalesce(func.sum(Order.total), 0),
            func.coalesce(func.sum(Order.total - Order.cost_total), 0),
        )
        .where(*conditions)
        .group_by(local_day)
        .order_by(local_day)
    ).all()

    return (
        "Sales summary",
        ["Date", "Orders", "Subtotal", "Discounts", "Tax", "Total", "Gross margin"],
        [[str(r[0]), r[1], _m(r[2]), _m(r[3]), _m(r[4]), _m(r[5]), _m(r[6])] for r in rows],
    )


def _sales_detailed(session, tenant, start, end, branch_id):
    conditions = [
        Order.status != OrderStatus.DRAFT,
        Order.completed_at >= start,
        Order.completed_at < end,
    ]
    if branch_id:
        conditions.append(Order.branch_id == branch_id)

    rows = session.execute(
        select(
            Order.order_number,
            Order.completed_at,
            OrderItem.product_name,
            OrderItem.sku,
            OrderItem.quantity,
            OrderItem.unit_price,
            OrderItem.discount_amount,
            OrderItem.tax_amount,
            OrderItem.line_total,
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(*conditions)
        .order_by(Order.completed_at, Order.order_number)
    ).all()

    return (
        "Sales detail",
        ["Receipt", "When", "Product", "SKU", "Qty", "Unit", "Discount", "Tax", "Line total"],
        [
            [
                r[0],
                r[1].strftime("%Y-%m-%d %H:%M") if r[1] else "",
                r[2],
                r[3] or "",
                _d(r[4]),
                _m(r[5]),
                _m(r[6]),
                _m(r[7]),
                _m(r[8]),
            ]
            for r in rows
        ],
    )


def _tax_report(session, tenant, start, end, branch_id):
    """Grouped by rate, which is how a return is actually filed."""
    conditions = [_SOLD, Order.completed_at >= start, Order.completed_at < end]
    if branch_id:
        conditions.append(Order.branch_id == branch_id)

    rows = session.execute(
        select(
            OrderItem.tax_rate,
            OrderItem.tax_inclusive,
            func.count(OrderItem.id),
            func.coalesce(func.sum(OrderItem.line_total - OrderItem.tax_amount), 0),
            func.coalesce(func.sum(OrderItem.tax_amount), 0),
            func.coalesce(func.sum(OrderItem.line_total), 0),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(*conditions)
        .group_by(OrderItem.tax_rate, OrderItem.tax_inclusive)
        .order_by(OrderItem.tax_rate)
    ).all()

    return (
        "Tax report",
        ["Rate", "Basis", "Lines", "Net", "Tax", "Gross"],
        [
            [
                f"{_d(r[0]) * 100:.2f}%",
                "Inclusive" if r[1] else "Exclusive",
                r[2],
                _m(r[3]),
                _m(r[4]),
                _m(r[5]),
            ]
            for r in rows
        ],
    )


def _inventory_report(session, tenant, start, end, branch_id):
    conditions = [Product.deleted_at.is_(None), Product.track_stock.is_(True)]
    if branch_id:
        conditions.append(StockItem.branch_id == branch_id)

    rows = session.execute(
        select(
            Product.sku,
            Product.name,
            Branch.name,
            StockItem.quantity,
            Product.cost_price,
            Product.price,
            StockItem.quantity * Product.cost_price,
        )
        .select_from(StockItem)
        .join(Product, Product.id == StockItem.product_id)
        .join(Branch, Branch.id == StockItem.branch_id)
        .where(*conditions)
        .order_by(Product.name)
    ).all()

    return (
        "Inventory valuation",
        ["SKU", "Product", "Branch", "On hand", "Cost", "Price", "Stock value"],
        [[r[0], r[1], r[2], _d(r[3]), _m(r[4]), _m(r[5]), _m(r[6])] for r in rows],
    )


def _employee_report(session, tenant, start, end, branch_id):
    conditions = [_SOLD, Order.completed_at >= start, Order.completed_at < end]
    if branch_id:
        conditions.append(Order.branch_id == branch_id)

    rows = session.execute(
        select(
            User.full_name,
            User.role,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0),
            func.coalesce(func.avg(Order.total), 0),
            func.coalesce(func.sum(Order.discount_total), 0),
        )
        .join(User, User.id == Order.cashier_id)
        .where(*conditions)
        .group_by(User.full_name, User.role)
        .order_by(func.sum(Order.total).desc())
    ).all()

    return (
        "Employee performance",
        ["Employee", "Role", "Orders", "Revenue", "Average basket", "Discounts given"],
        [[r[0], r[1].value, r[2], _m(r[3]), _m(r[4]), _m(r[5])] for r in rows],
    )


BUILDERS = {
    ReportType.SALES_SUMMARY: _sales_summary,
    ReportType.SALES_DETAILED: _sales_detailed,
    ReportType.TAX: _tax_report,
    ReportType.INVENTORY: _inventory_report,
    ReportType.EMPLOYEE_PERFORMANCE: _employee_report,
}


# --------------------------------------------------------------------------
# Renderers
# --------------------------------------------------------------------------


def render_csv(headers: list[str], rows: list[list[Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    # utf-8-sig: without the BOM, Excel mangles accented product names, which
    # is the single most common complaint about exported CSVs.
    return buffer.getvalue().encode("utf-8-sig")


def render_pdf(
    title: str,
    headers: list[str],
    rows: list[list[Any]],
    *,
    shop_name: str,
    period: str,
    currency: str,
) -> bytes:
    buffer = io.BytesIO()
    # Landscape: these tables are wide, and a wrapped column is unreadable.
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{title} - {shop_name}",
    )

    styles = getSampleStyleSheet()
    heading = ParagraphStyle("H", parent=styles["Heading1"], fontSize=16, spaceAfter=2)
    sub = ParagraphStyle(
        "S", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#666666")
    )

    story: list[Any] = [
        Paragraph(f"{shop_name} — {title}", heading),
        Paragraph(f"{period} · amounts in {currency}", sub),
        Spacer(1, 8 * mm),
    ]

    if not rows:
        story.append(Paragraph("No data for this period.", styles["Normal"]))
    else:
        table_data = [headers] + [
            [f"{cell:,.2f}" if isinstance(cell, Decimal) else str(cell) for cell in row]
            for row in rows
        ]
        numeric_columns = [
            index for index, cell in enumerate(rows[0]) if isinstance(cell, Decimal | int)
        ]
        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                    # Zebra striping: these run to hundreds of rows and the eye
                    # loses the line without it.
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#fafafa")],
                    ),
                ]
                + [("ALIGN", (col, 1), (col, -1), "RIGHT") for col in numeric_columns]
            )
        )
        story.append(table)

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}", sub))

    doc.build(story)
    return buffer.getvalue()


def generate(
    session: Session,
    *,
    tenant: Tenant,
    report_type: ReportType,
    export_format: ReportFormat,
    start: datetime,
    end: datetime,
    branch_id: uuid.UUID | None,
    job_id: uuid.UUID,
) -> tuple[Path, int]:
    builder = BUILDERS.get(report_type)
    if builder is None:
        raise ValueError(f"No builder for {report_type}")

    title, headers, rows = builder(session, tenant, start, end, branch_id)

    if export_format is ReportFormat.PDF:
        payload = render_pdf(
            title,
            headers,
            rows,
            shop_name=tenant.name,
            period=f"{start.date()} to {end.date()}",
            currency=tenant.currency,
        )
        suffix = "pdf"
    else:
        payload = render_csv(headers, rows)
        suffix = "csv"

    # Namespaced per tenant, so a mistaken or tampered job id cannot reach
    # another shop's export.
    directory = Path(settings.REPORT_STORAGE_DIR) / str(tenant.id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{job_id}.{suffix}"
    path.write_bytes(payload)
    return path, len(payload)
