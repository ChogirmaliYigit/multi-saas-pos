from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ProductUnit
from app.schemas.common import ORMModel


class CategoryOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    color: str | None
    image_url: str | None
    sort_order: int
    parent_id: uuid.UUID | None


class ProductOut(ORMModel):
    id: uuid.UUID
    name: str
    sku: str
    barcode: str | None
    category_id: uuid.UUID | None
    unit: ProductUnit
    price: Decimal
    image_url: str | None
    track_stock: bool
    is_favorite: bool
    tax_rate: Decimal = Field(default=Decimal("0"))
    tax_inclusive: bool = False
    # Stock for the branch the terminal is on. None when untracked.
    stock_quantity: Decimal | None = None
    low_stock: bool = False


class ProductListItem(ProductOut):
    """The catalog list row.

    Cost and margin are owner/manager data: a cashier browsing the POS grid
    has no business seeing what the shop pays for a can of cola. These fields
    are populated only when the caller holds PRODUCT_COST_READ, and are None
    otherwise -- omitted at the source rather than hidden in the UI.
    """

    cost_price: Decimal | None = None
    category_name: str | None = None
    low_stock_threshold: Decimal | None = None
    is_active: bool = True


class ProductLookupOut(BaseModel):
    """Result of a barcode scan.

    `pack_size` is why this is not just a product lookup: scanning a carton
    barcode should add six units, not one.
    """

    product: ProductOut
    pack_size: Decimal = Decimal("1")
    matched_on: str  # "barcode" | "sku" | "pack_barcode"


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None
    color: str | None = Field(default=None, max_length=9)
    image_url: str | None = Field(default=None, max_length=500)
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None
    color: str | None = Field(default=None, max_length=9)
    image_url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None
    is_active: bool | None = None


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str = Field(min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    description: str | None = None
    category_id: uuid.UUID | None = None
    tax_rate_id: uuid.UUID | None = None
    unit: ProductUnit = ProductUnit.PIECE
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    cost_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    image_url: str | None = Field(default=None, max_length=500)
    track_stock: bool = True
    low_stock_threshold: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True
    is_favorite: bool = False
    # Opening stock for the default branch, written as an INITIAL movement.
    opening_stock: Decimal | None = Field(default=None, ge=0)

    @field_validator("sku", "barcode")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    description: str | None = None
    category_id: uuid.UUID | None = None
    tax_rate_id: uuid.UUID | None = None
    unit: ProductUnit | None = None
    price: Decimal | None = Field(default=None, ge=0)
    cost_price: Decimal | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
    track_stock: bool | None = None
    low_stock_threshold: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    is_favorite: bool | None = None


class ProductDetail(ProductOut):
    """The admin view. Includes cost and margin, which the POS never sees --
    a cashier does not need to know the shop's buying price."""

    description: str | None = None
    cost_price: Decimal
    category_name: str | None = None
    tax_rate_id: uuid.UUID | None = None
    tax_rate_name: str | None = None
    low_stock_threshold: Decimal
    is_active: bool

    @property
    def margin(self) -> Decimal:
        if self.price <= 0:
            return Decimal("0")
        return (self.price - self.cost_price) / self.price


class TaxRateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rate: Decimal = Field(ge=0, le=1, max_digits=6, decimal_places=4)
    is_inclusive: bool = False
    is_default: bool = False
    is_active: bool = True


class TaxRateOut(ORMModel):
    id: uuid.UUID
    name: str
    rate: Decimal
    is_inclusive: bool
    is_default: bool
    is_active: bool
