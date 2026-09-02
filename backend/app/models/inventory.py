from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import StockMovementType

if TYPE_CHECKING:
    from app.models.catalog import Product
    from app.models.tenant import Branch


class StockItem(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Current on-hand quantity for one product in one branch.

    This is the only mutable quantity in the system. Checkout updates it with
    `UPDATE ... SET quantity = quantity - :qty` inside the order transaction,
    so two terminals selling the last unit cannot both win.
    """

    __tablename__ = "stock_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "branch_id", "product_id", name="uq_stock_items_scope"),
        # Drives the "low stock" dashboard widget without a table scan.
        Index("ix_stock_items_low_stock", "tenant_id", "branch_id", "quantity"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    # Held by parked/draft carts so two cashiers do not promise the same unit.
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    # Overrides Product.low_stock_threshold when set (a flagship branch may
    # want a deeper buffer than a kiosk).
    low_stock_threshold: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    last_counted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    branch: Mapped[Branch] = relationship()
    product: Mapped[Product] = relationship(back_populates="stock_items")

    @property
    def available_quantity(self) -> Decimal:
        return self.quantity - self.reserved_quantity


class StockMovement(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Append-only ledger. Every change to a StockItem writes one row here, so
    on-hand quantity is always reconstructable and shrinkage is auditable.
    Rows are never updated or deleted."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("ix_stock_movements_product_time", "tenant_id", "product_id", "created_at"),
        Index("ix_stock_movements_reference", "tenant_id", "reference_type", "reference_id"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL")
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    movement_type: Mapped[StockMovementType] = mapped_column(
        Enum(StockMovementType, name="stock_movement_type"), nullable=False, index=True
    )
    # Signed: sales and waste are negative, purchases and returns positive.
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    # Polymorphic pointer: ("order", <order_id>), ("transfer", <transfer_id>)...
    reference_type: Mapped[str | None] = mapped_column(String(32))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
