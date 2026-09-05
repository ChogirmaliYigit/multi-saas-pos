"""Branches, shop settings, tax rates, and self-service profile edits."""

from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import text

from app.db.seed_demo import seed_demo
from app.db.session import engine

SIGNUP = {
    "shop_name": "Corner Store",
    "slug": "corner",
    "owner_name": "Dana Owner",
    "email": "dana@corner.example",
    "password": "correct-horse-battery",
    "currency": "USD",
    "country_code": "US",
    "plan_code": "pro",  # basic caps branches at 1; these tests need headroom
}


async def owner(client: AsyncClient, *, seed: bool = True) -> dict[str, str]:
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    if seed:
        await seed_demo("corner")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"], "tenant_slug": "corner"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# --------------------------------------------------------------------------
# Branches
# --------------------------------------------------------------------------


async def test_signup_branch_is_listed_as_the_default(client: AsyncClient):
    headers = await owner(client)
    resp = await client.get("/api/v1/branches", headers=headers)
    assert resp.status_code == 200, resp.text
    branches = resp.json()
    assert len(branches) == 1
    assert branches[0]["is_default"] is True
    assert branches[0]["is_active"] is True


async def test_creating_a_branch_moves_the_default_flag(client: AsyncClient):
    headers = await owner(client)
    created = await client.post(
        "/api/v1/branches",
        json={"name": "Airport kiosk", "code": "air", "is_default": True},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "AIR"  # normalised, it prefixes receipts

    branches = (await client.get("/api/v1/branches", headers=headers)).json()
    assert [b["is_default"] for b in branches].count(True) == 1
    assert next(b for b in branches if b["is_default"])["code"] == "AIR"


async def test_branch_codes_are_unique_within_a_shop(client: AsyncClient):
    headers = await owner(client)
    await client.post("/api/v1/branches", json={"name": "Second", "code": "TWO"}, headers=headers)
    clash = await client.post(
        "/api/v1/branches", json={"name": "Third", "code": "two"}, headers=headers
    )
    assert clash.status_code == 409
    assert clash.json()["code"] == "code_taken"


async def test_the_last_branch_cannot_be_deleted(client: AsyncClient):
    """A shop with no branch has nowhere to hold stock or ring up a sale."""
    headers = await owner(client)
    only = (await client.get("/api/v1/branches", headers=headers)).json()[0]

    resp = await client.delete(f"/api/v1/branches/{only['id']}", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "last_branch"


async def test_the_default_branch_cannot_be_deleted_or_deactivated(client: AsyncClient):
    headers = await owner(client)
    default = (await client.get("/api/v1/branches", headers=headers)).json()[0]
    await client.post("/api/v1/branches", json={"name": "Second", "code": "TWO"}, headers=headers)

    deleted = await client.delete(f"/api/v1/branches/{default['id']}", headers=headers)
    assert deleted.status_code == 409
    assert deleted.json()["code"] == "default_branch"

    deactivated = await client.patch(
        f"/api/v1/branches/{default['id']}", json={"is_active": False}, headers=headers
    )
    assert deactivated.status_code == 409


async def test_closing_a_branch_keeps_its_sales(client: AsyncClient):
    """Soft delete, always: a receipt reprinted next year still has to name
    where it was rung up."""
    headers = await owner(client)
    second = (
        await client.post(
            "/api/v1/branches", json={"name": "Second", "code": "TWO"}, headers=headers
        )
    ).json()

    closed = await client.delete(f"/api/v1/branches/{second['id']}", headers=headers)
    assert closed.status_code == 200, closed.text

    assert [b["id"] for b in (await client.get("/api/v1/branches", headers=headers)).json()] == [
        b["id"]
        for b in (await client.get("/api/v1/branches", headers=headers)).json()
        if b["id"] != second["id"]
    ]

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        deleted_at = await conn.scalar(
            text("SELECT deleted_at FROM branches WHERE id = :id"), {"id": second["id"]}
        )
    assert deleted_at is not None


async def test_branch_quota_is_enforced_by_plan(client: AsyncClient):
    await client.post("/api/v1/auth/signup", json={**SIGNUP, "plan_code": "basic"})
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"], "tenant_slug": "corner"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(
        "/api/v1/branches", json={"name": "Second", "code": "TWO"}, headers=headers
    )
    assert resp.status_code == 402, resp.text
    assert resp.json()["details"]["resource"] == "branches"


async def test_a_cashier_cannot_manage_branches(client: AsyncClient):
    headers = await owner(client)
    await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Sam Cashier",
            "email": "sam@corner.example",
            "password": "till-operator-pass",
            "role": "cashier",
        },
        headers=headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "sam@corner.example",
            "password": "till-operator-pass",
            "tenant_slug": "corner",
        },
    )
    cashier = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(
        "/api/v1/branches", json={"name": "Rogue", "code": "RGE"}, headers=cashier
    )
    assert resp.status_code == 403


async def test_branches_are_not_visible_across_shops(client: AsyncClient):
    headers = await owner(client)
    await client.post(
        "/api/v1/branches", json={"name": "Airport kiosk", "code": "AIR"}, headers=headers
    )

    await client.post(
        "/api/v1/auth/signup",
        json={**SIGNUP, "slug": "rival", "email": "eve@rival.example", "shop_name": "Rival"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "eve@rival.example",
            "password": SIGNUP["password"],
            "tenant_slug": "rival",
        },
    )
    rival = {"Authorization": f"Bearer {login.json()['access_token']}"}

    codes = {b["code"] for b in (await client.get("/api/v1/branches", headers=rival)).json()}
    assert "AIR" not in codes


# --------------------------------------------------------------------------
# Shop settings
# --------------------------------------------------------------------------


async def test_shop_settings_round_trip(client: AsyncClient):
    headers = await owner(client)
    resp = await client.patch(
        "/api/v1/shop",
        json={
            "name": "Corner Store & Deli",
            "tax_number": "GB123456789",
            "address": "12 High Street",
            "receipt_footer": "Thank you!",
            "timezone": "Europe/London",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Corner Store & Deli"

    fresh = await client.get("/api/v1/shop", headers=headers)
    assert fresh.json()["receipt_footer"] == "Thank you!"
    assert fresh.json()["slug"] == "corner"


async def test_settings_json_is_merged_not_replaced(client: AsyncClient):
    """Sending one switch must not silently wipe the rest of the config."""
    headers = await owner(client)
    await client.patch(
        "/api/v1/shop", json={"settings": {"cash_rounding": "0.05"}}, headers=headers
    )
    await client.patch("/api/v1/shop", json={"settings": {"receipt_width_mm": 58}}, headers=headers)

    settings = (await client.get("/api/v1/shop", headers=headers)).json()["settings"]
    assert settings["cash_rounding"] == "0.05"
    assert settings["receipt_width_mm"] == 58


async def test_currency_and_slug_are_not_self_service(client: AsyncClient):
    """Currency is stamped on every past order; the slug is how people log in.
    Both are ignored rather than accepted."""
    headers = await owner(client)
    await client.patch(
        "/api/v1/shop", json={"currency": "EUR", "slug": "hijacked"}, headers=headers
    )

    shop = (await client.get("/api/v1/shop", headers=headers)).json()
    assert shop["currency"] == "USD"
    assert shop["slug"] == "corner"


async def test_a_cashier_cannot_edit_shop_settings(client: AsyncClient):
    headers = await owner(client)
    await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Sam Cashier",
            "email": "sam@corner.example",
            "password": "till-operator-pass",
            "role": "cashier",
        },
        headers=headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "sam@corner.example",
            "password": "till-operator-pass",
            "tenant_slug": "corner",
        },
    )
    cashier = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.patch("/api/v1/shop", json={"name": "Sams Store"}, headers=cashier)
    assert resp.status_code == 403


async def test_settings_edits_do_not_reach_another_shop(client: AsyncClient):
    headers = await owner(client)
    await client.post(
        "/api/v1/auth/signup",
        json={**SIGNUP, "slug": "rival", "email": "eve@rival.example", "shop_name": "Rival"},
    )
    await client.patch("/api/v1/shop", json={"name": "Renamed"}, headers=headers)

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        name = await conn.scalar(text("SELECT name FROM tenants WHERE slug = 'rival'"))
    assert name == "Rival"


# --------------------------------------------------------------------------
# Tax rates
# --------------------------------------------------------------------------


async def test_editing_a_tax_rate_does_not_rewrite_past_sales(client: AsyncClient):
    """Last quarter's return must not change because a rate changed today."""
    headers = await owner(client)
    rates = (await client.get("/api/v1/catalog/tax-rates", headers=headers)).json()
    standard = next(r for r in rates if Decimal(r["rate"]) > 0)

    product = (
        await client.post(
            "/api/v1/catalog/products",
            json={
                "name": "Taxed thing",
                "sku": "TAX-1",
                "price": "100.00",
                "tax_rate_id": standard["id"],
                "opening_stock": "10",
            },
            headers=headers,
        )
    ).json()

    await client.post("/api/v1/shifts/open", json={"opening_float": "0"}, headers=headers)
    sale = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": product["id"], "quantity": "1"}],
            "payments": [{"method": "card", "amount": "120.00"}],
        },
        headers=headers,
    )
    order = sale.json()
    tax_at_the_time = Decimal(order["tax_total"])
    assert tax_at_the_time > 0

    bumped = await client.patch(
        f"/api/v1/catalog/tax-rates/{standard['id']}", json={"rate": "0.99"}, headers=headers
    )
    assert bumped.status_code == 200, bumped.text

    unchanged = await client.get(f"/api/v1/orders/{order['id']}", headers=headers)
    assert Decimal(unchanged.json()["tax_total"]) == tax_at_the_time


async def test_a_tax_rate_in_use_cannot_be_deleted(client: AsyncClient):
    headers = await owner(client)
    rates = (await client.get("/api/v1/catalog/tax-rates", headers=headers)).json()
    standard = next(r for r in rates if Decimal(r["rate"]) > 0)
    await client.post(
        "/api/v1/catalog/products",
        json={"name": "Taxed", "sku": "TAX-2", "price": "1.00", "tax_rate_id": standard["id"]},
        headers=headers,
    )

    resp = await client.delete(f"/api/v1/catalog/tax-rates/{standard['id']}", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "rate_in_use"
    assert resp.json()["details"]["products"] >= 1
    assert str(resp.json()["details"]["products"]) in resp.json()["message"]


async def test_an_unused_tax_rate_can_be_removed(client: AsyncClient):
    headers = await owner(client)
    created = (
        await client.post(
            "/api/v1/catalog/tax-rates",
            json={"name": "Luxury", "rate": "0.30"},
            headers=headers,
        )
    ).json()

    resp = await client.delete(f"/api/v1/catalog/tax-rates/{created['id']}", headers=headers)
    assert resp.status_code == 200, resp.text

    remaining = (await client.get("/api/v1/catalog/tax-rates", headers=headers)).json()
    assert created["id"] not in {r["id"] for r in remaining}


async def test_only_one_tax_rate_is_default(client: AsyncClient):
    headers = await owner(client)
    created = (
        await client.post(
            "/api/v1/catalog/tax-rates", json={"name": "Luxury", "rate": "0.30"}, headers=headers
        )
    ).json()
    await client.patch(
        f"/api/v1/catalog/tax-rates/{created['id']}", json={"is_default": True}, headers=headers
    )

    rates = (await client.get("/api/v1/catalog/tax-rates", headers=headers)).json()
    assert [r["is_default"] for r in rates].count(True) == 1


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------


async def test_profile_edits_apply_to_the_signed_in_user(client: AsyncClient):
    headers = await owner(client)
    resp = await client.patch(
        "/api/v1/auth/me",
        json={"full_name": "Dana O. Owner", "phone": "+1 555 0100"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["full_name"] == "Dana O. Owner"

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["user"]["phone"] == "+1 555 0100"


async def test_profile_edits_cannot_escalate_privileges(client: AsyncClient):
    """role, branch, and permissions are granted by someone else."""
    headers = await owner(client)
    await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Sam Cashier",
            "email": "sam@corner.example",
            "password": "till-operator-pass",
            "role": "cashier",
        },
        headers=headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "sam@corner.example",
            "password": "till-operator-pass",
            "tenant_slug": "corner",
        },
    )
    cashier = {"Authorization": f"Bearer {login.json()['access_token']}"}

    await client.patch(
        "/api/v1/auth/me",
        json={
            "full_name": "Sam Owner",
            "role": "owner",
            "permission_overrides": ["tenant.update"],
            "is_active": True,
        },
        headers=cashier,
    )

    me = (await client.get("/api/v1/auth/me", headers=cashier)).json()
    assert me["user"]["full_name"] == "Sam Owner"
    assert me["user"]["role"] == "cashier"
    assert "tenant.update" not in me["permissions"]


async def test_branch_listing_survives_row_level_security(client: AsyncClient):
    """The endpoint runs as the unprivileged app role, so RLS is live here."""
    headers = await owner(client)
    await client.post(
        "/api/v1/branches", json={"name": "Airport kiosk", "code": "AIR"}, headers=headers
    )
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        tenant_id = await conn.scalar(text("SELECT id FROM tenants WHERE slug = 'corner'"))

    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        assert await conn.scalar(text("SELECT count(*) FROM branches")) == 2
