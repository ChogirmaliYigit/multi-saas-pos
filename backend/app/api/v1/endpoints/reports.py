from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import CurrentTenant, CurrentUser, DbSession, require, resolve_branch_id
from app.core.config import settings
from app.core.exceptions import APIError, NotFoundError
from app.core.permissions import Permission
from app.models.audit import ReportJob
from app.models.enums import ReportStatus
from app.schemas.common import Page
from app.schemas.reports import ReportJobOut, ReportRequest

router = APIRouter(prefix="/reports", tags=["reports"])


def _to_out(job: ReportJob) -> ReportJobOut:
    return ReportJobOut(
        **{
            field: getattr(job, field)
            for field in ReportJobOut.model_fields
            if field != "is_downloadable" and hasattr(job, field)
        },
        is_downloadable=(job.status is ReportStatus.COMPLETED and bool(job.file_url)),
    )


@router.post(
    "",
    response_model=ReportJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require(Permission.REPORT_EXPORT))],
)
async def request_report(
    payload: ReportRequest,
    db: DbSession,
    user: CurrentUser,
    tenant: CurrentTenant,
) -> ReportJobOut:
    """Queue an export.

    Returns 202 with a job, not the file. A year of sales is not something to
    render inside an HTTP request, and a browser that times out mid-download
    leaves the user with nothing to retry.
    """
    try:
        tz = ZoneInfo(tenant.timezone)
    except Exception:
        tz = UTC

    # Interpret the dates in the shop's timezone, and make date_to inclusive:
    # a user asking for "1st to 5th" means the whole of the 5th.
    start = datetime.combine(payload.date_from, time.min, tzinfo=tz)
    end = datetime.combine(payload.date_to, time.min, tzinfo=tz) + timedelta(days=1)

    job = ReportJob(
        tenant_id=tenant.id,
        requested_by_id=user.id,
        branch_id=resolve_branch_id(user, payload.branch_id),
        report_type=payload.report_type,
        export_format=payload.export_format,
        status=ReportStatus.PENDING,
        params={
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "label": f"{payload.date_from} to {payload.date_to}",
        },
    )
    db.add(job)
    await db.flush()

    # Import here so the API process never needs a broker connection just to
    # import its router -- the web container starts even if Redis is down.
    from app.worker.tasks import generate_report

    try:
        async_result = generate_report.delay(str(job.id))
        job.celery_task_id = async_result.id
    except Exception:
        # Queueing failed (broker unreachable). Mark it rather than leaving a
        # job stuck on "pending" that nothing will ever pick up.
        job.status = ReportStatus.FAILED
        job.error_message = "Report queue is unavailable. Try again shortly."

    await db.flush()
    return _to_out(job)


@router.get(
    "",
    response_model=Page[ReportJobOut],
    dependencies=[Depends(require(Permission.REPORT_READ))],
)
async def list_reports(
    db: DbSession,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
) -> Page[ReportJobOut]:
    total = await db.scalar(select(func.count()).select_from(ReportJob))
    rows = await db.scalars(
        select(ReportJob)
        .order_by(ReportJob.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return Page[ReportJobOut](
        items=[_to_out(row) for row in rows], total=total or 0, page=page, size=size
    )


@router.get(
    "/{job_id}",
    response_model=ReportJobOut,
    dependencies=[Depends(require(Permission.REPORT_READ))],
)
async def get_report(job_id: uuid.UUID, db: DbSession) -> ReportJobOut:
    """Polled by the frontend while the worker runs."""
    job = await db.scalar(select(ReportJob).where(ReportJob.id == job_id))
    if job is None:
        raise NotFoundError("Report not found.")
    return _to_out(job)


@router.get(
    "/{job_id}/download",
    dependencies=[Depends(require(Permission.REPORT_EXPORT))],
)
async def download_report(job_id: uuid.UUID, db: DbSession, tenant: CurrentTenant) -> FileResponse:
    """Stream the generated file.

    Served through the API rather than a static path so it stays behind
    authentication -- a report contains a shop's entire trading history.
    """
    job = await db.scalar(select(ReportJob).where(ReportJob.id == job_id))
    if job is None:
        raise NotFoundError("Report not found.")
    if job.status is not ReportStatus.COMPLETED or not job.file_url:
        raise APIError("That report is not ready yet.", code="report_not_ready")

    path = Path(job.file_url).resolve()
    # Defence in depth: the row already passed RLS, but confirm the path sits
    # inside this tenant's directory before opening anything off disk.
    expected_root = (Path(settings.REPORT_STORAGE_DIR) / str(tenant.id)).resolve()
    if not path.is_relative_to(expected_root) or not path.exists():
        raise NotFoundError("That report file has expired.", code="report_expired")

    suffix = "csv" if job.export_format.value == "csv" else job.export_format.value
    filename = f"{job.report_type.value}-{job.params.get('label', 'export')}.{suffix}"
    return FileResponse(
        path,
        filename=filename,
        media_type="text/csv" if suffix == "csv" else "application/pdf",
    )
