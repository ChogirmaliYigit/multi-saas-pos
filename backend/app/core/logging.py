from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import settings
from app.core.context import get_principal, get_request_id


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with request_id and tenant_id attached.

    Structured from the start because the alternative -- grepping multi-line
    tracebacks across tenants on a VPS -- does not scale past the first
    incident.
    """

    def format(self, record: logging.LogRecord) -> str:
        principal = get_principal()
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
            "tenant_id": str(principal.tenant_id) if principal and principal.tenant_id else None,
            "user_id": str(principal.user_id) if principal else None,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if settings.is_production
        else logging.Formatter("%(levelname)-8s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL)

    # Uvicorn installs its own handlers; route them through ours.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers = [handler]
        logging.getLogger(name).propagate = False
