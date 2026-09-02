from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import StockMovementType
from app.schemas.common import ORMModel


class StockLevelOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    sku: str
    barcode: str | None
    branch_id: uuid.UUID
    branch_name: str
    quantity: Decimal
    reserved_quantity: Decimal
    available: Decimal
    low_stock_threshold: Decimal
    is_low: bool
    unit: str
    cost_price: Decimal
    # quantity * cost, so an owner can see what is sitting on the shelves.
    stock_value: Decimal


class StockAdjustIn(BaseModel):
    product_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    movement_type: StockMovementType = StockMovementType.ADJUSTMENT
    # Signed. Negative for waste and corrections downward.
    quantity: Decimal = Field(max_digits=14, decimal_places=3)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    supplier_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class StockCountIn(BaseModel):
    """A physical count. Sets an absolute figure rather than a delta, and the
    ledger records the difference -- which is the shrinkage number."""

    product_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    counted_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    note: str | None = Field(default=None, max_length=500)


class StockMovementOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    branch_id: uuid.UUID
    movement_type: StockMovementType
    quantity: Decimal
    quantity_after: Decimal
    unit_cost: Decimal | None
    reference_type: str | None
    reference_id: uuid.UUID | None
    note: str | None
    created_at: datetime
    created_by_id: uuid.UUID | None


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = None
    notes: str | None = None
    is_active: bool = True


class SupplierOut(ORMModel):
    id: uuid.UUID
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    is_active: bool
