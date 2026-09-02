from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import (
    OptionalTenantMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.tenant import Branch, Tenant


class User(Base, UUIDPrimaryKeyMixin, OptionalTenantMixin, TimestampMixin, SoftDeleteMixin):
    """Every human in the system: SaaS operators and shop staff alike.

    tenant_id is NULL *only* for SUPER_ADMIN. That is the one deliberate
    exception to the tenant-scoping rule, and it is enforced by a CHECK
    constraint rather than left to application discipline.
    """

    __tablename__ = "users"
    __table_args__ = (
        # Same email may exist in two different shops, but only once per shop.
        Index(
            "uq_users_tenant_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND tenant_id IS NOT NULL"),
        ),
        # Platform staff share one global namespace.
        Index(
            "uq_users_platform_email",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND tenant_id IS NULL"),
        ),
        CheckConstraint(
            "(role = 'SUPER_ADMIN' AND tenant_id IS NULL) OR "
            "(role <> 'SUPER_ADMIN' AND tenant_id IS NOT NULL)",
            name="ck_users_super_admin_has_no_tenant",
        ),
    )

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # Argon2 hash of a 4-6 digit PIN for switching cashiers mid-shift without
    # typing a full password on a tablet. Not unique: argon2 is salted, so
    # equal PINs hash differently and a unique index would be decorative.
    # PIN login therefore identifies the user first (tap avatar), then
    # verifies -- one hash comparison, not a scan of every cashier.
    pin_hash: Mapped[str | None] = mapped_column(String(255))

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.CASHIER, index=True
    )
    # Per-user grants/denies layered on top of the role defaults,
    # e.g. {"deny": ["order.refund"], "allow": ["report.export"]}
    permission_overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant: Mapped[Tenant | None] = relationship(back_populates="users")
    branch: Mapped[Branch | None] = relationship()
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_platform_staff(self) -> bool:
        return self.role is UserRole.SUPER_ADMIN


class RefreshToken(Base, UUIDPrimaryKeyMixin, OptionalTenantMixin, TimestampMixin):
    """Rotating refresh tokens. Only the SHA-256 digest is stored, so a
    database leak does not hand out live sessions."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when this token is rotated, so replay of an old token can be detected
    # and the whole family revoked.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )

    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
