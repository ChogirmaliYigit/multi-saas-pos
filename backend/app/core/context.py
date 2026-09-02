from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import NamedTuple

from app.models.enums import UserRole


class RequestPrincipal(NamedTuple):
    """The verified identity behind the current request or Celery task."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID | None
    role: UserRole
    branch_id: uuid.UUID | None = None

    @property
    def is_platform_staff(self) -> bool:
        return self.role is UserRole.SUPER_ADMIN


# Set by TenantContextMiddleware from the *verified* JWT and by Celery task
# wrappers. Read by the DB session (SET LOCAL) and the ORM tenant filter.
# ContextVar, not a global, so concurrent requests on one worker cannot see
# each other's tenant.
_principal: ContextVar[RequestPrincipal | None] = ContextVar("principal", default=None)
_tenant_id: ContextVar[uuid.UUID | None] = ContextVar("tenant_id", default=None)
# Slug parsed from the Host header, e.g. shop1.saas-pos.com -> "shop1".
_tenant_slug: ContextVar[str | None] = ContextVar("tenant_slug", default=None)
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_principal() -> RequestPrincipal | None:
    return _principal.get()


def set_principal(principal: RequestPrincipal | None) -> None:
    _principal.set(principal)
    _tenant_id.set(principal.tenant_id if principal else None)


def get_current_tenant_id() -> uuid.UUID | None:
    return _tenant_id.get()


def get_tenant_slug() -> str | None:
    return _tenant_slug.get()


def set_tenant_slug(slug: str | None) -> None:
    _tenant_slug.set(slug)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def reset_context() -> None:
    _principal.set(None)
    _tenant_id.set(None)
    _tenant_slug.set(None)
    _request_id.set(None)


@contextmanager
def tenant_scope(tenant_id: uuid.UUID | None) -> Iterator[None]:
    """Bind a tenant for the ORM filter only.

    This moves the Python-side context but NOT the Postgres GUC that RLS
    reads. When a database session is involved, use
    `app.db.session.session_tenant_scope` instead -- it moves both, and the
    two disagreeing is a bug that surfaces as a confusing RLS rejection.
    """
    token = _tenant_id.set(tenant_id)
    try:
        yield
    finally:
        _tenant_id.reset(token)
