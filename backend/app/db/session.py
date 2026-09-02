from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.context import get_current_tenant_id, get_principal, tenant_scope

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    # Recycle below typical cloud-LB idle timeouts so a pooled connection is
    # never handed out already dead.
    pool_recycle=1800,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def bind_tenant_guc(session: AsyncSession) -> None:
    """Bind the current tenant to the transaction for Postgres RLS.

    `set_config(..., is_local => true)` is the parameterisable form of
    `SET LOCAL`: it is scoped to the transaction and is discarded on
    commit or rollback. That property is the whole point -- a connection
    returned to the pool cannot carry one shop's context into the next
    request served by that connection.
    """
    principal = get_principal()
    tenant_id = get_current_tenant_id()

    await session.execute(
        text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": str(tenant_id) if tenant_id else ""},
    )
    # Platform staff need to read across shops (support, MRR rollups). This is
    # the single, explicit escape hatch from RLS, and it is only ever set from
    # a signature-verified SUPER_ADMIN token.
    await session.execute(
        text("SELECT set_config('app.is_platform', :flag, true)"),
        {"flag": "on" if principal and principal.is_platform_staff else "off"},
    )


@asynccontextmanager
async def session_tenant_scope(
    session: AsyncSession, tenant_id: uuid.UUID | None
) -> AsyncIterator[None]:
    """Switch tenant for both isolation layers at once.

    The ORM filter reads a ContextVar; the RLS policy reads a transaction GUC.
    Moving only one of them is the subtle failure mode here -- the ORM would
    happily build the INSERT and Postgres would reject it (or, worse in the
    other direction, the ORM would filter while the policy stayed wide open).
    So they are never changed independently: this is the only supported way to
    re-scope a session mid-transaction.

    Needed by genuinely tenant-crossing operations: signup (which creates the
    shop it then writes into), platform admin tooling, and Celery tasks that
    loop over shops.
    """
    previous = await session.scalar(text("SELECT current_setting('app.current_tenant', true)"))
    with tenant_scope(tenant_id):
        await session.execute(
            text("SELECT set_config('app.current_tenant', :tenant, true)"),
            {"tenant": str(tenant_id) if tenant_id else ""},
        )
        try:
            yield
        finally:
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tenant, true)"),
                {"tenant": previous or ""},
            )


@asynccontextmanager
async def auth_lookup_scope(session: AsyncSession) -> AsyncIterator[None]:
    """Open the narrow RLS escape hatch that authentication needs.

    Logging in must read `users` and write `refresh_tokens` before any tenant
    is known -- there is no session yet to derive one from. Rather than leave
    those tables outside RLS entirely, the policy accepts one named GUC, and
    this is the only place that sets it. Re-entrant, and restored on exit, so
    it can never stay on for the rest of a request.
    """
    previous = await session.scalar(text("SELECT current_setting('app.auth_lookup', true)"))
    await session.execute(text("SELECT set_config('app.auth_lookup', 'on', true)"))
    try:
        yield
    finally:
        await session.execute(
            text("SELECT set_config('app.auth_lookup', :prev, true)"),
            {"prev": previous or "off"},
        )


@asynccontextmanager
async def platform_scope(session: AsyncSession) -> AsyncIterator[None]:
    """Act as the platform for the length of this block.

    The one legitimate way to read or write across shops: bootstrap seeds,
    super-admin tooling, and Celery rollups. It is a named, restored-on-exit
    scope rather than a loosened policy, so every cross-tenant operation in the
    codebase is greppable.

    Never reachable from a tenant request -- `get_db` sets this GUC only from a
    signature-verified SUPER_ADMIN token.
    """
    previous = await session.scalar(text("SELECT current_setting('app.is_platform', true)"))
    await session.execute(text("SELECT set_config('app.is_platform', 'on', true)"))
    try:
        yield
    finally:
        await session.execute(
            text("SELECT set_config('app.is_platform', :prev, true)"),
            {"prev": previous or "off"},
        )


async def get_db() -> AsyncIterator[AsyncSession]:
    """Request-scoped session. One transaction per request: commit on success,
    roll back on any exception, so a half-written sale can never persist."""
    async with AsyncSessionLocal() as session:
        try:
            await bind_tenant_guc(session)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()
