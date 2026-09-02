from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    currency: str
    revenue_today: Decimal
    revenue_yesterday: Decimal
    orders_today: int
    average_basket: Decimal
    gross_margin_today: Decimal
    revenue_month: Decimal
    low_stock_count: int
    out_of_stock_count: int
    active_shifts: int

    @property
    def revenue_change_pct(self) -> Decimal | None:
        if self.revenue_yesterday <= 0:
            return None
        return ((self.revenue_today - self.revenue_yesterday) / self.revenue_yesterday) * 100


class RevenuePoint(BaseModel):
    day: date
    revenue: Decimal
    orders: int
    margin: Decimal


class TopProduct(BaseModel):
    product_id: uuid.UUID | None
    name: str
    sku: str | None
    quantity_sold: Decimal
    revenue: Decimal
    margin: Decimal


class LowStockItem(BaseModel):
    product_id: uuid.UUID
    name: str
    sku: str
    branch_id: uuid.UUID
    branch_name: str
    quantity: Decimal
    threshold: Decimal


class PaymentBreakdown(BaseModel):
    method: str
    total: Decimal
    count: int


class SalesByHour(BaseModel):
    hour: int
    revenue: Decimal
    orders: int
