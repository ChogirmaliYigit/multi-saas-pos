from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AccountLockedError,
    ConflictError,
    InvalidCredentialsError,
    NotFoundError,
    TenantInactiveError,
    TenantResolutionError,
)
from app.core.security import (
    create_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
    verify_pin,
)
from app.db.session import AsyncSessionLocal, auth_lookup_scope, session_tenant_scope
from app.db.tenant_filter import SKIP_TENANT_FILTER
from app.models.enums import (
    BillingCycle,
    SubscriptionStatus,
    TenantStatus,
    UserRole,
)
from app.models.subscription import Plan, Subscription
from app.models.tenant import Branch, Tenant
from app.models.user import RefreshToken, User
from app.schemas.auth import SignupRequest, TokenPair

_NO_FILTER = {SKIP_TENANT_FILTER: True}


def _now() -> datetime:
    return datetime.now(UTC)


async def _record_failed_attempt(user_id: uuid.UUID) -> None:
    """Increment the lockout counter in its OWN transaction.

    The request that triggered this is about to raise, and the request-scoped
    session rolls back on the way out -- taking the counter with it. A lockout
    that is undone by the very failure it counts protects nothing, so this
    commits independently.
    """
    async with AsyncSessionLocal() as session:
        async with auth_lookup_scope(session):
            user = await session.scalar(
                select(User).where(User.id == user_id).execution_options(**_NO_FILTER)
            )
            if user is None:
                return
            user.failed_login_count += 1
            if user.failed_login_count >= settings.MAX_FAILED_LOGINS:
                user.locked_until = _now() + timedelta(minutes=settings.LOCKOUT_MINUTES)
                user.failed_login_count = 0
            await session.commit()


async def _revoke_all_in_new_transaction(user_id: uuid.UUID) -> None:
    """Same reasoning as above: revocation triggered by detected token theft
    must survive the 401 that follows it."""
    async with AsyncSessionLocal() as session:
        async with auth_lookup_scope(session):
            await _revoke_all_for_user(session, user_id)
            await session.commit()


async def resolve_tenant_by_slug(db: AsyncSession, slug: str) -> Tenant:
    tenant = await db.scalar(
        select(Tenant)
        .where(Tenant.slug == slug, Tenant.deleted_at.is_(None))
        .execution_options(**_NO_FILTER)
    )
    if tenant is None:
        raise TenantResolutionError()
    return tenant


async def issue_token_pair(
    db: AsyncSession,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenPair:
    """Mint an access/refresh pair and persist only the refresh digest.

    Runs under the auth escape hatch because at login time no tenant is bound
    yet, and the refresh_tokens row it writes carries one.
    """
    lifetime_minutes = (
        settings.POS_ACCESS_TOKEN_EXPIRE_MINUTES
        if user.role is UserRole.CASHIER
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token, _, access_expires = create_token(
        subject=user.id,
        token_type="access",
        tenant_id=user.tenant_id,
        role=user.role.value,
        branch_id=user.branch_id,
        expires_delta=timedelta(minutes=lifetime_minutes),
    )
    refresh_token, _, refresh_expires = create_token(
        subject=user.id,
        token_type="refresh",
        tenant_id=user.tenant_id,
        role=user.role.value,
        branch_id=user.branch_id,
    )

    async with auth_lookup_scope(db):
        db.add(
            RefreshToken(
                user_id=user.id,
                tenant_id=user.tenant_id,
                token_hash=hash_refresh_token(refresh_token),
                expires_at=refresh_expires,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        )
        user.last_login_at = _now()
        user.failed_login_count = 0
        user.locked_until = None
        await db.flush()

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int((access_expires - _now()).total_seconds()),
    )


async def authenticate(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    tenant_slug: str | None,
) -> User:
    """Password login.

    The login lookup is the one read that legitimately crosses tenants: there
    is no session yet, so there is no tenant to filter by. It is explicitly
    opted out of the ORM filter, runs under the named RLS escape hatch, and is
    immediately narrowed to a single shop -- either the subdomain's, or the
    platform namespace (tenant_id IS NULL).
    """
    stmt = (
        select(User)
        .where(
            func.lower(User.email) == email.lower(),
            User.deleted_at.is_(None),
        )
        .execution_options(**_NO_FILTER)
    )

    if tenant_slug:
        tenant = await resolve_tenant_by_slug(db, tenant_slug)
        if not tenant.is_operational:
            raise TenantInactiveError(tenant.blocked_reason or TenantInactiveError.message)
        stmt = stmt.where(User.tenant_id == tenant.id)
    else:
        # No shop context -> only platform staff may sign in here.
        stmt = stmt.where(User.tenant_id.is_(None))

    async with auth_lookup_scope(db):
        user = await db.scalar(stmt)

    if user is None:
        # Same error and roughly the same cost as a wrong password, so the
        # endpoint cannot be used to enumerate who works at a shop.
        hash_password(password)
        raise InvalidCredentialsError()

    if user.locked_until and user.locked_until > _now():
        raise AccountLockedError()

    if not verify_password(password, user.hashed_password):
        await _record_failed_attempt(user.id)
        raise InvalidCredentialsError()

    if not user.is_active:
        raise InvalidCredentialsError()

    # Transparent upgrade when the argon2 parameters have been raised.
    if password_needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)

    return user


async def authenticate_pin(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, pin: str
) -> User:
    """Cashier swap on an already-authenticated terminal.

    The user is identified first (avatar tap) and only then verified, so this
    is a single argon2 comparison rather than a scan over every cashier.
    """
    user = await db.scalar(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        )
    )
    if user is None or not user.is_active:
        raise InvalidCredentialsError("Incorrect PIN.")
    if user.locked_until and user.locked_until > _now():
        raise AccountLockedError()
    if not verify_pin(pin, user.pin_hash):
        await _record_failed_attempt(user.id)
        raise InvalidCredentialsError("Incorrect PIN.")
    return user


async def rotate_refresh_token(
    db: AsyncSession,
    *,
    presented_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenPair:
    """Single-use refresh tokens with reuse detection.

    If a token that was already rotated comes back, someone is replaying a
    stolen copy. We cannot tell the thief from the victim, so the whole token
    family is revoked and both are forced to sign in again.
    """
    digest = hash_refresh_token(presented_token)

    async with auth_lookup_scope(db):
        stored = await db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == digest)
            .execution_options(**_NO_FILTER)
        )
        if stored is None:
            raise InvalidCredentialsError("Invalid refresh token.")

        if stored.revoked_at is not None or stored.replaced_by_id is not None:
            await _revoke_all_in_new_transaction(stored.user_id)
            raise InvalidCredentialsError("Refresh token reuse detected; all sessions revoked.")

        if stored.expires_at <= _now():
            raise InvalidCredentialsError("Refresh token has expired.")

        user = await db.scalar(
            select(User)
            .where(User.id == stored.user_id, User.deleted_at.is_(None))
            .execution_options(**_NO_FILTER)
        )

    if user is None or not user.is_active:
        raise InvalidCredentialsError()

    if user.tenant_id is not None:
        tenant = await db.scalar(
            select(Tenant).where(Tenant.id == user.tenant_id).execution_options(**_NO_FILTER)
        )
        if tenant is None or not tenant.is_operational:
            raise TenantInactiveError()

    pair = await issue_token_pair(db, user, user_agent=user_agent, ip_address=ip_address)

    async with auth_lookup_scope(db):
        new_token = await db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(pair.refresh_token))
            .execution_options(**_NO_FILTER)
        )
        stored.revoked_at = _now()
        stored.replaced_by_id = new_token.id if new_token else None
        await db.flush()

    return pair


async def revoke_refresh_token(db: AsyncSession, presented_token: str) -> None:
    digest = hash_refresh_token(presented_token)
    async with auth_lookup_scope(db):
        stored = await db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == digest)
            .execution_options(**_NO_FILTER)
        )
        if stored and stored.revoked_at is None:
            stored.revoked_at = _now()
            await db.flush()


async def _revoke_all_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    tokens = await db.scalars(
        select(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .execution_options(**_NO_FILTER)
    )
    now = _now()
    for token in tokens:
        token.revoked_at = now


async def signup(db: AsyncSession, payload: SignupRequest) -> tuple[Tenant, User]:
    """Create shop + owner + default branch + trial subscription atomically.

    Runs inside the request transaction, so a failure at any step leaves no
    half-created shop behind.
    """
    existing = await db.scalar(
        select(Tenant.id).where(Tenant.slug == payload.slug).execution_options(**_NO_FILTER)
    )
    if existing:
        raise ConflictError("That shop address is already taken.", code="slug_taken")

    plan = await db.scalar(
        select(Plan)
        .where(Plan.code == payload.plan_code, Plan.is_active.is_(True))
        .execution_options(**_NO_FILTER)
    )
    if plan is None:
        raise NotFoundError("Unknown plan.", code="plan_not_found")

    now = _now()
    trial_end = now + timedelta(days=plan.trial_days)

    tenant = Tenant(
        name=payload.shop_name,
        slug=payload.slug,
        email=payload.email,
        currency=payload.currency.upper(),
        country_code=payload.country_code.upper(),
        timezone=payload.timezone,
        status=TenantStatus.TRIAL,
        trial_ends_at=trial_end,
    )
    db.add(tenant)
    await db.flush()  # assigns tenant.id

    # Everything below is tenant-owned; bind the context so the before_flush
    # stamp and the RLS policy both see the new shop.
    async with session_tenant_scope(db, tenant.id):
        branch = Branch(
            tenant_id=tenant.id,
            name=payload.shop_name,
            code="MAIN",
            is_default=True,
        )
        db.add(branch)
        await db.flush()

        owner = User(
            tenant_id=tenant.id,
            branch_id=branch.id,
            email=payload.email.lower(),
            full_name=payload.owner_name,
            hashed_password=hash_password(payload.password),
            role=UserRole.OWNER,
            is_active=True,
        )
        db.add(owner)

        db.add(
            Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status=SubscriptionStatus.TRIALING,
                billing_cycle=BillingCycle.MONTHLY,
                unit_amount=plan.price_monthly,
                currency=plan.currency,
                current_period_start=now,
                current_period_end=trial_end,
                trial_ends_at=trial_end,
            )
        )
        await db.flush()

    return tenant, owner
