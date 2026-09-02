"""Background tasks.

Workers run outside a request, so nothing sets the tenant context for them.
`_tenant_session` does the same two things `get_db` does per request -- bind
the RLS GUC and the ORM filter -- because a Celery task querying with no
tenant bound would either see nothing (fail closed, by design) or, if the
escape hatch were misused, see everything.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.context import tenant_scope
from app.db.tenant_filter import SKIP_TENANT_FILTER
from app.models.audit import ReportJob
from app.models.enums import ReportStatus
from app.models.tenant import Tenant
from app.services import report_service
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Workers use the sync driver with the same unprivileged role as the API, so
# RLS constrains them identically.
_engine = create_engine(
    settings.CELERY_DATABASE_URI, pool_pre_ping=True, pool_size=5, max_overflow=5
)
_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def _tenant_session(tenant_id: uuid.UUID | None) -> Iterator[Session]:
    """A worker session bound to one tenant, both layers together."""
    session = _SessionLocal()
    try:
        session.execute(
            text("SELECT set_config('app.current_tenant', :tenant, true)"),
            {"tenant": str(tenant_id) if tenant_id else ""},
        )
        session.execute(text("SELECT set_config('app.is_platform', 'off', true)"))
        with tenant_scope(tenant_id):
            yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _mark(job_id: uuid.UUID, **fields) -> None:
    """Status updates commit on their own connection.

    A failure marker written inside the job's transaction would roll back with
    the failure it is recording, leaving the job stuck on "running" forever --
    the same trap as the login lockout counter in Step 2.
    """
    session = _SessionLocal()
    try:
        session.execute(text("SELECT set_config('app.is_platform', 'on', true)"))
        job = session.get(ReportJob, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        session.commit()
    finally:
        session.close()


@celery_app.task(name="app.worker.tasks.generate_report", bind=True, max_retries=2)
def generate_report(self, job_id: str) -> dict:
    job_uuid = uuid.UUID(job_id)
    _mark(job_uuid, status=ReportStatus.RUNNING, started_at=datetime.now(UTC))

    try:
        session = _SessionLocal()
        try:
            session.execute(text("SELECT set_config('app.is_platform', 'on', true)"))
            job = session.get(ReportJob, job_uuid)
            if job is None:
                return {"status": "missing"}
            tenant_id = job.tenant_id
            params = dict(job.params or {})
            report_type = job.report_type
            export_format = job.export_format
            branch_id = job.branch_id
        finally:
            session.close()

        with _tenant_session(tenant_id) as scoped:
            tenant = scoped.scalar(
                select(Tenant)
                .where(Tenant.id == tenant_id)
                .execution_options(**{SKIP_TENANT_FILTER: True})
            )
            if tenant is None:
                raise ValueError("Tenant no longer exists")

            start = datetime.fromisoformat(params["date_from"])
            end = datetime.fromisoformat(params["date_to"])

            path, size = report_service.generate(
                scoped,
                tenant=tenant,
                report_type=report_type,
                export_format=export_format,
                start=start,
                end=end,
                branch_id=branch_id,
                job_id=job_uuid,
            )

        expires = datetime.now(UTC).timestamp() + settings.REPORT_RETENTION_HOURS * 3600
        _mark(
            job_uuid,
            status=ReportStatus.COMPLETED,
            file_url=str(path),
            file_size_bytes=size,
            completed_at=datetime.now(UTC),
            expires_at=datetime.fromtimestamp(expires, UTC),
        )
        return {"status": "completed", "bytes": size}

    except SoftTimeLimitExceeded:
        _mark(
            job_uuid,
            status=ReportStatus.FAILED,
            error_message="Report timed out. Try a shorter date range.",
            completed_at=datetime.now(UTC),
        )
        raise
    except Exception as exc:
        logger.exception("Report %s failed", job_id)
        _mark(
            job_uuid,
            status=ReportStatus.FAILED,
            # The user sees this string, so it must not leak SQL or paths.
            error_message="Could not generate this report.",
            completed_at=datetime.now(UTC),
        )
        raise self.retry(exc=exc, countdown=30) from exc


@celery_app.task(name="app.worker.tasks.purge_expired_reports")
def purge_expired_reports() -> dict:
    """Generated files are not kept forever; they contain a shop's full
    trading history and sit on disk unencrypted."""
    removed = 0
    session = _SessionLocal()
    try:
        session.execute(text("SELECT set_config('app.is_platform', 'on', true)"))
        expired = session.scalars(
            select(ReportJob)
            .where(
                ReportJob.expires_at.is_not(None),
                ReportJob.expires_at < datetime.now(UTC),
                ReportJob.file_url.is_not(None),
            )
            .execution_options(**{SKIP_TENANT_FILTER: True})
        ).all()

        for job in expired:
            try:
                Path(job.file_url).unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove %s", job.file_url)
            job.file_url = None
            removed += 1
        session.commit()
    finally:
        session.close()

    return {"removed": removed}
