"""Celery application.

Reports run out of band because a year of sales is not something to generate
inside a 30-second HTTP request. The API creates a `report_jobs` row, returns
it immediately, and the worker fills in `file_url` when the file is on disk.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "pos",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # A report still running after nine minutes is stuck, not slow.
    task_soft_time_limit=540,
    task_time_limit=600,
    # Redelivery on worker crash. Generation is idempotent -- it writes one
    # file and updates one row -- so at-least-once delivery is safe.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    beat_schedule={
        "purge-expired-reports": {
            "task": "app.worker.tasks.purge_expired_reports",
            "schedule": 3600.0,
        },
    },
)
