from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.mixins import (
    OptionalTenantMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import ReportFormat, ReportStatus, ReportType


class AuditLog(Base, UUIDPrimaryKeyMixin, OptionalTenantMixin, TimestampMixin):
    """Who changed what. tenant_id is nullable so platform-level actions
    (blocking a shop, changing a plan) are captured in the same stream."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_time", "tenant_id", "created_at"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    action: Mapped[str] = mapped_column(String(64), nullable=False)  # product.update, order.refund
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # {"price": {"old": "3.50", "new": "3.90"}}
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)


class ReportJob(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A Celery-backed export. The API returns this row immediately and the
    worker fills in file_url when the CSV/PDF is on disk (or S3)."""

    __tablename__ = "report_jobs"
    __table_args__ = (Index("ix_report_jobs_tenant_status", "tenant_id", "status", "created_at"),)

    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE")
    )

    report_type: Mapped[ReportType] = mapped_column(
        Enum(ReportType, name="report_type"), nullable=False
    )
    export_format: Mapped[ReportFormat] = mapped_column(
        Enum(ReportFormat, name="report_format"), nullable=False, default=ReportFormat.CSV
    )
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"), nullable=False, default=ReportStatus.PENDING
    )
    # {"date_from": "...", "date_to": "...", "branch_ids": [...]}
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    celery_task_id: Mapped[str | None] = mapped_column(String(64), index=True)
    file_url: Mapped[str | None] = mapped_column(String(500))
    file_size_bytes: Mapped[int | None] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Generated files are purged by a periodic beat task.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
