from __future__ import annotations

import uuid

import jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.context import (
    RequestPrincipal,
    reset_context,
    set_principal,
    set_request_id,
    set_tenant_slug,
)
from app.core.security import decode_token
from app.models.enums import UserRole


def extract_subdomain(host: str, base_domain: str) -> str | None:
    """shop1.saas-pos.com + saas-pos.com -> "shop1". Anything else -> None."""
    host = host.split(":")[0].lower().strip()
    base = base_domain.split(":")[0].lower().strip()
    if not host or host == base or not host.endswith("." + base):
        return None
    label = host[: -(len(base) + 1)]
    # Only a single leading label counts; www/api/admin are platform hosts.
    if "." in label or label in {"www", "api", "admin", "app"}:
        return None
    return label or None


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Layer 1 of tenant isolation.

    Establishes *who* and *which shop* for the request, from the verified JWT
    only. The subdomain is read too, but purely as a cross-check -- it can
    never widen access, because a mismatch is rejected rather than trusted.

    Requests with no or invalid credentials are passed through with an empty
    context; the route dependencies decide whether that is a 401. Doing the
    rejection here would break /health, /docs and the login endpoint itself.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        reset_context()

        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        set_request_id(request_id)
        request.state.request_id = request_id

        slug = extract_subdomain(request.headers.get("host", ""), settings.BASE_DOMAIN)
        set_tenant_slug(slug)
        request.state.tenant_slug = slug

        principal = self._principal_from_header(request)
        set_principal(principal)
        request.state.principal = principal

        try:
            response = await call_next(request)
        finally:
            reset_context()

        response.headers["X-Request-ID"] = request_id
        return response

    @staticmethod
    def _principal_from_header(request: Request) -> RequestPrincipal | None:
        auth = request.headers.get("authorization", "")
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        try:
            payload = decode_token(token, expected_type="access")
        except jwt.PyJWTError:
            # Malformed/expired tokens produce an anonymous context. The
            # dependency raises the 401 with a proper error body.
            return None

        try:
            tenant_raw = payload.get("tid")
            branch_raw = payload.get("bid")
            return RequestPrincipal(
                user_id=uuid.UUID(payload["sub"]),
                tenant_id=uuid.UUID(tenant_raw) if tenant_raw else None,
                role=UserRole(payload["role"]),
                branch_id=uuid.UUID(branch_raw) if branch_raw else None,
            )
        except (KeyError, ValueError):
            return None
