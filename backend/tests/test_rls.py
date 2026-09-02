"""Layer 3 of tenant isolation, tested against a real PostgreSQL.

These assertions are about the *database*, not the application. They must hold
even if every line of Python above them is wrong.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.rls import all_protected_tables
from app.db.session import engine


async def _make_tenant(conn, slug: str) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO tenants (id, name, slug, email, country_code, currency, "
            "timezone, locale, status, settings, created_at, updated_at) "
            "VALUES (:id, :slug, :slug, 'a@b.co', 'US', 'USD', 'UTC', 'en', "
            "'ACTIVE', '{}'::jsonb, now(), now())"
        ),
        {"id": tenant_id, "slug": slug},
    )
    await conn.execute(
        text(
            "INSERT INTO branches (id, tenant_id, name, code, is_default, is_active, "
            "created_at, updated_at) VALUES (:id, :tid, 'Main', 'MAIN', true, true, now(), now())"
        ),
        {"id": uuid.uuid4(), "tid": tenant_id},
    )
    return tenant_id


async def test_every_tenant_owned_table_has_a_policy():
    """A new tenant-scoped model must not be able to ship without RLS.

    Covers `users` too: its tenant_id is nullable, which is exactly the
    property that would let it slip out of an isolation scheme keyed on a
    NOT NULL column.
    """
    expected = set(all_protected_tables())
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_policies WHERE policyname = 'tenant_isolation'")
        )
        actual = {r[0] for r in rows}
    assert expected <= actual, f"missing RLS policy on: {sorted(expected - actual)}"


async def test_forced_rls_is_on_for_every_policy_table():
    """ENABLE alone exempts the table owner; FORCE is what closes that gap."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT relname FROM pg_class WHERE relname = ANY(:tables) "
                "AND (relrowsecurity IS FALSE OR relforcerowsecurity IS FALSE)"
            ),
            {"tables": all_protected_tables()},
        )
        unforced = [r[0] for r in rows]
    assert unforced == [], f"RLS not forced on: {unforced}"


async def test_app_role_cannot_bypass_rls():
    """The whole design rests on the runtime role being unprivileged."""
    async with engine.connect() as conn:
        row = await conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles " "WHERE rolname = current_user")
        )
        is_super, can_bypass = row.one()
    assert not is_super, "API is connected as a superuser; RLS would be a no-op"
    assert not can_bypass, "API role has BYPASSRLS; RLS would be a no-op"


async def test_select_cannot_see_another_tenants_rows():
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        tenant_a = await _make_tenant(conn, "rls-shop-a")
        tenant_b = await _make_tenant(conn, "rls-shop-b")
        for tid, name in ((tenant_a, "A-Widget"), (tenant_b, "B-Widget")):
            await conn.execute(
                text(
                    "INSERT INTO products (id, tenant_id, name, sku, unit, price, "
                    "cost_price, track_stock, low_stock_threshold, is_active, "
                    "is_favorite, created_at, updated_at) "
                    "VALUES (:id, :tid, :name, :sku, 'PIECE', 1, 0, true, 0, true, "
                    "false, now(), now())"
                ),
                {"id": uuid.uuid4(), "tid": tid, "name": name, "sku": name},
            )

    # Now read as the application would: scoped to tenant A.
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(tenant_a)},
        )
        await conn.execute(text("SELECT set_config('app.is_platform', 'off', true)"))
        names = (await conn.execute(text("SELECT name FROM products"))).scalars().all()

    assert names == ["A-Widget"], f"tenant A saw {names}"


async def test_insert_for_another_tenant_is_rejected():
    """WITH CHECK stops a compromised handler from *writing* into another
    shop, which a read-only policy would happily allow."""
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        tenant_a = await _make_tenant(conn, "rls-write-a")
        tenant_b = await _make_tenant(conn, "rls-write-b")

    with pytest.raises(Exception) as excinfo:
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_a)},
            )
            await conn.execute(text("SELECT set_config('app.is_platform', 'off', true)"))
            await conn.execute(
                text(
                    "INSERT INTO products (id, tenant_id, name, sku, unit, price, "
                    "cost_price, track_stock, low_stock_threshold, is_active, "
                    "is_favorite, created_at, updated_at) "
                    "VALUES (:id, :tid, 'sneaky', 'SNEAK', 'PIECE', 1, 0, true, 0, "
                    "true, false, now(), now())"
                ),
                {"id": uuid.uuid4(), "tid": tenant_b},
            )
    assert "row-level security" in str(excinfo.value).lower()


async def test_unset_tenant_context_sees_nothing():
    """A code path that forgets to bind a tenant returns zero rows rather than
    every shop's rows -- fail closed, not open."""
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        tenant = await _make_tenant(conn, "rls-unset")
        await conn.execute(
            text(
                "INSERT INTO products (id, tenant_id, name, sku, unit, price, "
                "cost_price, track_stock, low_stock_threshold, is_active, "
                "is_favorite, created_at, updated_at) "
                "VALUES (:id, :tid, 'x', 'X', 'PIECE', 1, 0, true, 0, true, false, "
                "now(), now())"
            ),
            {"id": uuid.uuid4(), "tid": tenant},
        )

    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.current_tenant', '', true)"))
        await conn.execute(text("SELECT set_config('app.is_platform', 'off', true)"))
        count = await conn.scalar(text("SELECT count(*) FROM products"))
    assert count == 0


async def test_users_table_is_isolated_between_shops():
    """The staff list is the most likely place for a tenancy bug to become a
    privacy incident, so it gets its own database-level assertion."""
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        tenant_a = await _make_tenant(conn, "rls-users-a")
        tenant_b = await _make_tenant(conn, "rls-users-b")
        for tid, email in ((tenant_a, "a@a.example"), (tenant_b, "b@b.example")):
            await conn.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, full_name, "
                    "hashed_password, role, permission_overrides, is_active, "
                    "failed_login_count, created_at, updated_at) "
                    "VALUES (:id, :tid, :email, 'Staff', 'x', 'CASHIER', "
                    "'{}'::jsonb, true, 0, now(), now())"
                ),
                {"id": uuid.uuid4(), "tid": tid, "email": email},
            )
        # A platform admin, belonging to no shop.
        await conn.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, full_name, "
                "hashed_password, role, permission_overrides, is_active, "
                "failed_login_count, created_at, updated_at) "
                "VALUES (:id, NULL, 'root@platform.example', 'Root', 'x', "
                "'SUPER_ADMIN', '{}'::jsonb, true, 0, now(), now())"
            ),
            {"id": uuid.uuid4()},
        )

    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(tenant_a)},
        )
        await conn.execute(text("SELECT set_config('app.is_platform', 'off', true)"))
        await conn.execute(text("SELECT set_config('app.auth_lookup', 'off', true)"))
        emails = (await conn.execute(text("SELECT email FROM users"))).scalars().all()

    assert emails == ["a@a.example"], f"shop A saw {emails}"


async def test_auth_escape_hatch_is_off_by_default():
    """The login escape hatch must never be on unless auth_lookup_scope set
    it -- otherwise every request would read every shop's users."""
    async with engine.connect() as conn:
        value = await conn.scalar(text("SELECT current_setting('app.auth_lookup', true)"))
    assert value in (None, "", "off")
