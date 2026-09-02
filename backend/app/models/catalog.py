from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import (
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import ProductUnit

if TYPE_CHECKING:
    from app.models.inventory import StockItem


class Category(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, SoftDeleteMixin):
    """Self-referencing tree. Colour drives the POS grid tiles."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_categories_tenant_slug"),)

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500))
    color: Mapped[str | None] = mapped_column(String(9))  # #RRGGBB for POS tiles
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    parent: Mapped[Category | None] = relationship(remote_side="Category.id")
    products: Mapped[list[Product]] = relationship(back_populates="category")


class TaxRate(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, SoftDeleteMixin):
    """VAT / sales-tax definitions. `is_inclusive` decides whether the shelf
    price already contains the tax -- it changes the whole cart maths, so it
    is stored per rate rather than assumed."""

    __tablename__ = "tax_rates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tax_rates_tenant_name"),
        CheckConstraint("rate >= 0 AND rate <= 1", name="ck_tax_rates_range"),
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)  # "VAT 12%"
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)  # 0.1200
    is_inclusive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Product(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, SoftDeleteMixin):
    """A sellable item. Stock levels live in `stock_items` (per branch), never
    on the product row -- a single quantity column cannot survive multi-branch
    or concurrent checkouts."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),
        # The hot path of the whole POS: scanner types a barcode, this index
        # answers it. Partial, so deleted rows never shadow a reused code.
        Index(
            "ix_products_tenant_barcode",
            "tenant_id",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("ix_products_tenant_category", "tenant_id", "category_id"),
        Index(
            "ix_products_tenant_name_trgm",
            "tenant_id",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        CheckConstraint("price >= 0 AND cost_price >= 0", name="ck_products_non_negative_price"),
    )

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    tax_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_rates.id", ondelete="SET NULL")
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64))  # primary EAN/UPC
    image_url: Mapped[str | None] = mapped_column(String(500))

    unit: Mapped[ProductUnit] = mapped_column(
        Enum(ProductUnit, name="product_unit"), nullable=False, default=ProductUnit.PIECE
    )
    # Weighed goods sell in 0.001 steps; pieces are forced to whole numbers by
    # the cart validator.
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    track_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    low_stock_threshold: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Pinned to the first page of the POS grid.
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    category: Mapped[Category | None] = relationship(back_populates="products")
    tax_rate: Mapped[TaxRate | None] = relationship()
    barcodes: Mapped[list[ProductBarcode]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    stock_items: Mapped[list[StockItem]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductBarcode(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Extra codes pointing at the same product -- a six-pack carton and the
    single can carry different EANs. `pack_size` lets one scan of the carton
    add 6 units to the cart."""

    __tablename__ = "product_barcodes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_product_barcodes_tenant_code"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_size: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=1)
    label: Mapped[str | None] = mapped_column(String(80))

    product: Mapped[Product] = relationship(back_populates="barcodes")


class Supplier(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_suppliers_tenant_name"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
