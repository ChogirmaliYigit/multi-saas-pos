from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import RequestPrincipal, get_principal
from app.core.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    SubscriptionRequiredError,
    TenantInactiveError,
)
from app.core.permissions import permissions_for
from app.db.session import get_db
from app.db.tenant_filter import SKIP_TENANT_FILTER
from app.models.enums import SubscriptionStatus, UserRole
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import User

# auto_error=False so unauthenticated requests reach our own exception
# handler and get the standard error envelope instead of FastAPI's.
bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    request: Request,
    _credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """Resolve the User behind the verified token.

    The token was already validated by the middleware; this re-checks the
    database state that a token cannot know about -- deactivated staff,
    deleted accounts, and shops suspended since the token was issued.
    """
    principal: RequestPrincipal | None = get_principal()
    if principal is None:
        raise AuthenticationError()

    user = await db.scalar(
        select(User)
        .where(User.id == principal.user_id, User.deleted_at.is_(None))
        .execution_options(**{SKIP_TENANT_FILTER: True})
    )
    if user is None or not user.is_active:
        raise AuthenticationError("Account is inactive or no longer exists.")

    # A token minted before a role change must not keep the old powers.
    if user.role is not principal.role or user.tenant_id != principal.tenant_id:
        raise AuthenticationError("Session is stale. Please sign in again.")

    # The subdomain never grants access, but a mismatch means the token is
    # being replayed against another shop's host -- refuse it.
    slug = getattr(request.state, "tenant_slug", None)
    if slug and user.tenant_id is not None:
        tenant_slug = await db.scalar(
            select(Tenant.slug)
            .where(Tenant.id == user.tenant_id)
            .execution_options(**{SKIP_TENANT_FILTER: True})
        )
        if tenant_slug != slug:
            raise PermissionDeniedError("Token does not belong to this shop.")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_tenant(db: DbSession, user: CurrentUser) -> Tenant:
    """The shop behind the request. Suspended shops are cut off here, which is
    what makes the super-admin block button take effect immediately rather
    than when tokens happen to expire."""
    if user.tenant_id is None:
        raise PermissionDeniedError("This endpoint requires a shop context.")

    tenant = await db.scalar(
        select(Tenant)
        .where(Tenant.id == user.tenant_id, Tenant.deleted_at.is_(None))
        .execution_options(**{SKIP_TENANT_FILTER: True})
    )
    if tenant is None:
        raise AuthenticationError("Shop no longer exists.")
    if not tenant.is_operational:
        raise TenantInactiveError(tenant.blocked_reason or TenantInactiveError.message)
    return tenant


CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]


async def require_active_subscription(db: DbSession, tenant: CurrentTenant) -> Subscription:
    """Gate write-heavy features on billing state. Reads stay open so a shop
    behind on payment can still access its own history."""
    subscription = await db.scalar(
        select(Subscription)
        .where(Subscription.tenant_id == tenant.id)
        .execution_options(**{SKIP_TENANT_FILTER: True})
    )
    if subscription is None:
        raise SubscriptionRequiredError()
    if subscription.status in (
        SubscriptionStatus.CANCELED,
        SubscriptionStatus.EXPIRED,
    ):
        raise SubscriptionRequiredError("Your subscription has ended.")
    return subscription


def require(*permissions: str) -> Callable[..., object]:
    """Route guard: `dependencies=[Depends(require(Permission.PRODUCT_MANAGE))]`.

    All listed permissions must be held (AND, not OR).
    """

    async def _dependency(user: CurrentUser) -> User:
        granted = permissions_for(user.role, user.permission_overrides)
        missing = [p for p in permissions if p not in granted]
        if missing:
            raise PermissionDeniedError(
                f"Missing permission: {', '.join(missing)}",
                details={"required": list(permissions), "missing": missing},
            )
        return user

    return _dependency


def require_roles(*roles: UserRole) -> Callable[..., object]:
    async def _dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDeniedError()
        return user

    return _dependency


async def get_platform_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.SUPER_ADMIN:
        # Same 403 as any other denial: do not confirm that a platform API
        # exists at this path to a tenant user probing for it.
        raise PermissionDeniedError()
    return user


PlatformAdmin = Annotated[User, Depends(get_platform_admin)]


def resolve_branch_id(user: User, requested: uuid.UUID | None) -> uuid.UUID | None:
    """Cashiers are pinned to their assigned branch; managers and owners may
    query any branch in their own shop (RLS still bounds that to the shop)."""
    if user.role is UserRole.CASHIER:
        return user.branch_id
    return requested or user.branch_id
