from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import (
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import TenantStatus

if TYPE_CHECKING:
    from app.models.subscription import Subscription
    from app.models.user import User


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """One shop / business. The root of every isolation boundary.

    `slug` doubles as the subdomain (shop1.saas-pos.com) and as the tenant
    resolver key for the middleware.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    tax_number: Mapped[str | None] = mapped_column(String(64))

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="US")

    # Localisation defaults inherited by every receipt and report.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    logo_url: Mapped[str | None] = mapped_column(String(500))
    receipt_header: Mapped[str | None] = mapped_column(Text)
    receipt_footer: Mapped[str | None] = mapped_column(Text)

    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"),
        nullable=False,
        default=TenantStatus.TRIAL,
        index=True,
    )
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Free-form per-shop switches (allow_negative_stock, receipt_width_mm,
    # rounding_mode, ...). Keeps the schema stable as features land.
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    branches: Mapped[list[Branch]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    users: Mapped[list[User]] = relationship(back_populates="tenant")
    subscription: Mapped[Subscription | None] = relationship(back_populates="tenant", uselist=False)

    @property
    def is_operational(self) -> bool:
        return self.status in (TenantStatus.TRIAL, TenantStatus.ACTIVE)


class Branch(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, SoftDeleteMixin):
    """A physical store location. Stock is always held per branch."""

    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_branches_tenant_code"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(32))
    timezone: Mapped[str | None] = mapped_column(String(64))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tenant: Mapped[Tenant] = relationship(back_populates="branches")
