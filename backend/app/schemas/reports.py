from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, model_validator

from app.models.enums import ReportFormat, ReportStatus, ReportType
from app.schemas.common import ORMModel


class ReportRequest(BaseModel):
    report_type: ReportType
    export_format: ReportFormat = ReportFormat.CSV
    date_from: date
    date_to: date
    branch_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _sane_range(self) -> ReportRequest:
        if self.date_to < self.date_from:
            raise ValueError("date_to must not be before date_from")
        # An unbounded range on a busy shop is a worker tied up for minutes
        # and a file nobody opens.
        if (self.date_to - self.date_from).days > 366:
            raise ValueError("Reports cover at most one year at a time")
        return self


class ReportJobOut(ORMModel):
    id: uuid.UUID
    report_type: ReportType
    export_format: ReportFormat
    status: ReportStatus
    params: dict
    branch_id: uuid.UUID | None
    file_size_bytes: int | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    # The path is deliberately not exposed; downloads go through the API so
    # they stay authenticated and tenant-scoped.
    is_downloadable: bool = False
