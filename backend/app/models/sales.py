from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import (
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import (
    DiscountType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ShiftStatus,
)

PAYMENT_METHOD_ENUM = Enum(PaymentMethod, name="payment_method")

if TYPE_CHECKING:
    from app.models.catalog import Product
    from app.models.tenant import Branch
    from app.models.user import User


class Customer(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, SoftDeleteMixin):
    """Optional walk-in identity for loyalty and receipt e-mailing."""

    __tablename__ = "customers"
    __table_args__ = (
        Index(
            "uq_customers_tenant_phone",
            "tenant_id",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("ix_customers_tenant_name", "tenant_id", "name"),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    loyalty_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Denormalised running totals, updated in the checkout transaction. Cheap
    # to recompute from orders if they ever drift.
    total_spent: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    store_credit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)


class Shift(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A cashier's till session. Closing one reconciles counted cash against
    what the system expected, which is how theft and miskeys get caught."""

    __tablename__ = "shifts"
    __table_args__ = (
        # One open shift per cashier per branch at a time.
        Index(
            "uq_shifts_one_open_per_user",
            "tenant_id",
            "branch_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
        ),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    status: Mapped[ShiftStatus] = mapped_column(
        Enum(ShiftStatus, name="shift_status"), nullable=False, default=ShiftStatus.OPEN
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    opening_float: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    expected_cash: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    counted_cash: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    cash_difference: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    cash_in: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    cash_out: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship()
    branch: Mapped[Branch] = relationship()


class Order(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A sale. Once COMPLETED the monetary columns are immutable -- corrections
    happen through Refund rows, never by editing history."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_number", name="uq_orders_tenant_number"),
        # Backs every dashboard/report query: "this tenant, this branch, this
        # date range", newest first.
        Index("ix_orders_tenant_branch_completed", "tenant_id", "branch_id", "completed_at"),
        Index("ix_orders_tenant_cashier", "tenant_id", "cashier_id", "completed_at"),
        Index("ix_orders_tenant_status", "tenant_id", "status"),
        CheckConstraint("total >= 0", name="ck_orders_total_non_negative"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    cashier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL")
    )
    shift_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="SET NULL"), index=True
    )

    # Human-facing, per-tenant, gapless-ish: "B1-20260901-0042".
    order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"), nullable=False, default=OrderStatus.DRAFT
    )

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(DiscountType, name="discount_type"), nullable=False, default=DiscountType.NONE
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    rounding_adjustment: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    paid_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    change_due: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    refunded_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    # Snapshot of cost at sale time -> gross margin reports never shift when
    # the purchase price changes later.
    cost_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    note: Mapped[str | None] = mapped_column(Text)
    receipt_printed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Client-generated key so a retried checkout on a flaky tablet connection
    # cannot create a duplicate sale.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    refunds: Mapped[list[Refund]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    customer: Mapped[Customer | None] = relationship()
    cashier: Mapped[User | None] = relationship()
    branch: Mapped[Branch] = relationship()


class OrderItem(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """One cart line. Product name, SKU, price and tax are *copied* here, not
    joined at read time -- a receipt reprinted next year must show what the
    customer actually paid, even if the product was renamed or deleted."""

    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_tenant_product", "tenant_id", "product_id"),
        CheckConstraint("quantity > 0", name="ck_order_items_positive_quantity"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )

    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64))
    barcode: Mapped[str | None] = mapped_column(String(64))

    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tax_inclusive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    refunded_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()


class Payment(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """One tender. Several rows per order supports split payment
    (e.g. $20 cash + remainder on card)."""

    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_tenant_method_time", "tenant_id", "method", "created_at"),)

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cashier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    method: Mapped[PaymentMethod] = mapped_column(PAYMENT_METHOD_ENUM, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), nullable=False, default=PaymentStatus.CAPTURED
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tendered_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    change_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    # Terminal/gateway echo only -- never a PAN. Card data does not enter this
    # database.
    reference: Mapped[str | None] = mapped_column(String(120))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="payments")


class Refund(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Reverses part or all of an order. Restocking writes its own
    StockMovement rows so the ledger stays complete."""

    __tablename__ = "refunds"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    shift_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="SET NULL")
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(PAYMENT_METHOD_ENUM, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    restocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # [{"order_item_id": ..., "quantity": "2.000", "amount": "19.98"}]
    line_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    order: Mapped[Order] = relationship(back_populates="refunds")


class OrderCounter(Base, TenantMixin, TimestampMixin):
    """Gapless per-branch, per-day receipt numbering.

    Most tax regimes want sequential receipt numbers, and "count the orders so
    far" is wrong under concurrency -- two tills would read the same count and
    mint the same number. This table is incremented with a single atomic
    upsert, so the database serialises it for us.

    Composite primary key rather than a surrogate id: the natural key *is* the
    identity, and a surrogate would allow duplicate (branch, period) rows.
    """

    __tablename__ = "order_counters"

    # Overrides TenantMixin's column so tenant_id participates in the key.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Local calendar day in the shop's timezone, e.g. "20260901".
    period: Mapped[str] = mapped_column(String(8), primary_key=True, nullable=False)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
