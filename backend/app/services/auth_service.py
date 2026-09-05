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
    generate_secret,
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
from app.models.user import PasswordResetToken, RefreshToken, User
from app.schemas.auth import SignupRequest, TokenPair
from app.services import email_service

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


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


async def request_password_reset(
    db: AsyncSession,
    *,
    email: str,
    tenant_slug: str | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Issue a reset link, if that address belongs to anyone.

    Returns nothing, always, and the endpoint answers identically whether or
    not the account exists. A "no such user" response here would turn the
    forgot-password form into a directory of who works at a shop -- and the
    people most likely to probe it are the ones a shop least wants finding
    out.
    """
    stmt = (
        select(User)
        .where(func.lower(User.email) == email.lower(), User.deleted_at.is_(None))
        .execution_options(**_NO_FILTER)
    )

    tenant: Tenant | None = None
    if tenant_slug:
        tenant = await db.scalar(
            select(Tenant)
            .where(Tenant.slug == tenant_slug, Tenant.deleted_at.is_(None))
            .execution_options(**_NO_FILTER)
        )
        if tenant is None:
            return
        stmt = stmt.where(User.tenant_id == tenant.id)
    else:
        stmt = stmt.where(User.tenant_id.is_(None))

    async with auth_lookup_scope(db):
        user = await db.scalar(stmt)

        if user is None or not user.is_active:
            return
        if tenant is not None and not tenant.is_operational:
            # A suspended shop cannot reset its way back in.
            return

        # Invalidate anything outstanding: a second request should not leave
        # two working links in two different inboxes.
        outstanding = await db.scalars(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .execution_options(**_NO_FILTER)
        )
        now = _now()
        for token in outstanding:
            token.used_at = now

        secret = generate_secret(32)
        db.add(
            PasswordResetToken(
                tenant_id=user.tenant_id,
                user_id=user.id,
                token_hash=hash_refresh_token(secret),
                expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES),
                requested_ip=ip_address,
                user_agent=user_agent,
            )
        )
        await db.flush()

    # The link goes to the frontend, which posts the token back to the API.
    base = settings.APP_BASE_URL.rstrip("/")
    reset_url = f"{base}/reset-password?token={secret}"
    if tenant_slug:
        reset_url += f"&shop={tenant_slug}"

    subject, text, html = email_service.password_reset_email(
        to=user.email,
        full_name=user.full_name,
        shop_name=tenant.name if tenant else None,
        reset_url=reset_url,
        ttl_minutes=settings.PASSWORD_RESET_TTL_MINUTES,
    )
    # Sent inline rather than queued: it is one small message, and a queue
    # would mean a reset silently fails whenever Redis is down. email_service
    # never raises, so a dead SMTP server cannot break the response.
    email_service.send(user.email, subject, text, html)


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> User:
    """Consume a reset token and set the new password."""
    digest = hash_refresh_token(token)

    async with auth_lookup_scope(db):
        record = await db.scalar(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == digest)
            .execution_options(**_NO_FILTER)
        )
        # One error for every failure mode -- unknown, expired and already
        # used are indistinguishable, so a probe learns nothing.
        if record is None or not record.is_usable:
            raise InvalidCredentialsError(
                "That reset link is invalid or has expired.",
                code="invalid_reset_token",
            )

        user = await db.scalar(
            select(User)
            .where(User.id == record.user_id, User.deleted_at.is_(None))
            .execution_options(**_NO_FILTER)
        )
        if user is None or not user.is_active:
            raise InvalidCredentialsError(
                "That reset link is invalid or has expired.",
                code="invalid_reset_token",
            )

        record.used_at = _now()
        user.hashed_password = hash_password(new_password)
        # A lockout should not outlive the reset that fixes it.
        user.failed_login_count = 0
        user.locked_until = None
        await db.flush()

    # Everything else is signed out. Someone resetting a password is often
    # doing it because they think an existing session is not theirs.
    await _revoke_all_in_new_transaction(user.id)
    return user
