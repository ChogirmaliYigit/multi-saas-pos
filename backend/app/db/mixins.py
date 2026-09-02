from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class UUIDPrimaryKeyMixin:
    """UUID v4 primary keys: safe to generate client-side (offline POS),
    and they do not leak row counts across tenants like serial ids do."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Products and users are never hard-deleted: historical orders must keep
    pointing at something, and tax authorities expect an immutable trail."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class TenantMixin:
    """Applied to every tenant-owned table.

    tenant_id is never accepted from the client. It is injected by the tenant
    middleware from the verified JWT, applied automatically to every query by
    the session-level filter, and enforced a third time by Postgres RLS.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


class OptionalTenantMixin:
    """For the two tables where tenant_id is legitimately NULL: `users` and
    `audit_logs`, whose platform-staff rows belong to no shop.

    They are still covered by both isolation layers -- the ORM filter and an
    RLS policy -- because `users` is, after orders, the most sensitive table in
    the system. Excluding it because the column is nullable is exactly the kind
    of quiet gap that makes a shop's staff list readable by another shop.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        )
