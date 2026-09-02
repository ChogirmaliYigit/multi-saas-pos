from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

# Importing the module registers the ORM-level tenant filter events.
import app.db.tenant_filter  # noqa: F401
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.context import get_request_id
from app.core.exceptions import APIError
from app.core.logging import configure_logging
from app.db.session import dispose_engine, engine
from app.middleware.tenant import TenantContextMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Starting %s (%s)", settings.PROJECT_NAME, settings.ENVIRONMENT)
    yield
    await dispose_engine()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json"
        if not settings.is_production
        else None,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # Order matters: the outermost middleware runs first. Tenant context must
    # be established before any route or dependency executes.
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    allow_origin_regex = None
    if settings.CORS_ALLOW_SUBDOMAIN_WILDCARD:
        base = settings.BASE_DOMAIN.replace(".", r"\.")
        allow_origin_regex = rf"^https?://([a-z0-9-]+\.)?{base}(:\d+)?$"

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Cross-origin responses expose almost no headers by default, so a
        # browser cannot read Content-Disposition and every report download
        # falls back to a generic filename. Content-Length lets a client show
        # real download progress.
        expose_headers=["X-Request-ID", "Content-Disposition", "Content-Length"],
    )

    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[settings.BASE_DOMAIN, f"*.{settings.BASE_DOMAIN}"],
        )

    _register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["ops"])
    async def readiness() -> JSONResponse:
        """Nginx and Compose use this: the process is only ready once it can
        actually reach the database."""
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - infrastructure path
            logger.error("Readiness probe failed: %s", exc)
            return JSONResponse(
                {"status": "unavailable", "database": "down"},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return JSONResponse({"status": "ready", "database": "up"})

    return app


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    """Reduce pydantic's error list to something safe to send back.

    Two problems with returning `exc.errors()` verbatim:

    1. `ctx` holds the original exception object for custom validators, which
       is not JSON-serialisable -- so any endpoint with a `field_validator`
       raising ValueError returned a 500 instead of a 422. That covered
       signup's slug rules, report date ranges, PIN format and role checks.
    2. `input` echoes the offending value straight back to the caller. On
       /auth/signup a too-short password would be returned in the error body,
       and from there into browser consoles and log aggregators.

    Only the field path, the message and the error type survive.
    """
    cleaned: list[dict[str, str]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        cleaned.append(
            {
                # Drop the leading "body"/"query" segment: the client cares
                # which field failed, not where FastAPI found it.
                "field": ".".join(str(part) for part in location[1:])
                or str(location[0] if location else ""),
                "message": str(error.get("msg", "Invalid value")),
                "type": str(error.get("type", "value_error")),
            }
        )
    return cleaned


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "validation_error",
                "message": "Some fields are invalid.",
                "details": {"errors": _safe_validation_errors(exc)},
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the detail, return none of it: stack traces and driver errors
        # leak schema and, in a multi-tenant system, sometimes other shops'
        # identifiers.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "internal_error",
                "message": "Something went wrong.",
                "details": {},
                "request_id": get_request_id(),
            },
        )


app = create_app()
