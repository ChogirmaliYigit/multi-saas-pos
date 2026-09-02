from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import DiscountType, OrderStatus, PaymentMethod
from app.schemas.common import ORMModel


class OrderItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: Decimal = Field(gt=0, decimal_places=3)
    discount_type: DiscountType = DiscountType.NONE
    discount_value: Decimal = Decimal("0")

    # Note there is no unit_price here, deliberately. Prices are read from the
    # database at checkout; a client that could name its own price would be a
    # discount button with no permission check.


class PaymentIn(BaseModel):
    method: PaymentMethod
    amount: Decimal = Field(gt=0)
    tendered_amount: Decimal | None = None
    reference: str | None = Field(default=None, max_length=120)
    card_last4: str | None = Field(default=None, max_length=4)


class OrderCreate(BaseModel):
    branch_id: uuid.UUID | None = None
    items: list[OrderItemIn] = Field(min_length=1)
    payments: list[PaymentIn] = Field(min_length=1)
    customer_id: uuid.UUID | None = None
    discount_type: DiscountType = DiscountType.NONE
    discount_value: Decimal = Decimal("0")
    note: str | None = Field(default=None, max_length=500)
    # Generated client-side per checkout attempt so a retry cannot double-charge.
    idempotency_key: str | None = Field(default=None, max_length=64)

    @field_validator("items")
    @classmethod
    def _cap_basket_size(cls, value: list[OrderItemIn]) -> list[OrderItemIn]:
        if len(value) > 500:
            raise ValueError("A single sale cannot exceed 500 lines")
        return value


class OrderItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str
    sku: str | None
    barcode: str | None
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    tax_inclusive: bool
    line_total: Decimal


class PaymentOut(ORMModel):
    id: uuid.UUID
    method: PaymentMethod
    amount: Decimal
    tendered_amount: Decimal | None
    reference: str | None
    card_last4: str | None


class OrderOut(ORMModel):
    id: uuid.UUID
    order_number: str
    status: OrderStatus
    branch_id: uuid.UUID
    cashier_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    rounding_adjustment: Decimal
    total: Decimal
    paid_total: Decimal
    change_due: Decimal
    currency: str
    note: str | None
    completed_at: datetime | None
    created_at: datetime
    items: list[OrderItemOut] = []
    payments: list[PaymentOut] = []


class ReceiptShop(BaseModel):
    name: str
    branch_name: str
    address: str | None
    phone: str | None
    tax_number: str | None
    header: str | None
    footer: str | None
    currency: str
    locale: str


class ReceiptOut(BaseModel):
    """Everything the printer needs, in one call.

    Assembled server-side so the ESC/POS bytes and the PDF are generated from
    identical data -- a receipt that differs between the paper copy and the
    reprint is a dispute waiting to happen.
    """

    order: OrderOut
    shop: ReceiptShop
    cashier_name: str | None
    customer_name: str | None
    printed_at: datetime
