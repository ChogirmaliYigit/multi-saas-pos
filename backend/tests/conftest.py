from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.context import reset_context
from app.db.seed import seed_plans
from app.db.session import AsyncSessionLocal
from app.main import create_app

# The runtime role deliberately has no TRUNCATE right, so fixtures clean up
# over a separate admin connection. That the app engine *cannot* do this is
# itself part of what the suite verifies.
admin_engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI.replace(
        f"{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}",
        f"{settings.POSTGRES_ADMIN_USER}:{settings.POSTGRES_ADMIN_PASSWORD}",
    ),
    poolclass=None,
)

# Tables wiped between tests, children before parents.
_TRUNCATE = """
TRUNCATE TABLE
    refresh_tokens, audit_logs, report_jobs,
    refunds, payments, order_items, orders, shifts,
    stock_movements, stock_items,
    product_barcodes, products, categories, tax_rates, suppliers, customers,
    subscription_invoices, subscriptions,
    users, branches, tenants,
    order_counters,
    -- plans too: the platform panel edits and retires tiers, and leaving them
    -- behind meant one test retiring "basic" broke signup for every test after
    -- it. seed_plans() recreates them, so each test starts from the same set.
    plans
RESTART IDENTITY CASCADE
"""


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    reset_context()
    # TRUNCATE needs owner rights, so it runs as the admin role via a raw
    # connection rather than the RLS-constrained app session.
    async with admin_engine.begin() as conn:
        await conn.execute(text(_TRUNCATE))
    await seed_plans()
    yield
    reset_context()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session
