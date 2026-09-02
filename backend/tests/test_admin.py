"""Tenant admin panel: catalog, inventory, employees, analytics, reports."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from app.db.seed_demo import seed_demo

SIGNUP = {
    "shop_name": "Corner Store",
    "slug": "corner",
    "owner_name": "Dana Owner",
    "email": "dana@corner.example",
    "password": "correct-horse-battery",
    "currency": "USD",
    "country_code": "US",
    "plan_code": "basic",
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


async def find_product(client: AsyncClient, headers: dict, sku: str) -> dict:
    resp = await client.get("/api/v1/catalog/products", params={"search": sku}, headers=headers)
    return resp.json()["items"][0]


# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------


async def test_create_product_with_opening_stock_writes_the_ledger(client: AsyncClient):
    """Opening stock must not appear from nowhere -- it goes through the same
    ledger as every other movement, so day-one stock is auditable."""
    headers = await owner(client)
    resp = await client.post(
        "/api/v1/catalog/products",
        json={
            "name": "Oat milk 1L",
            "sku": "DRK-900",
            "barcode": "5060123456789",
            "price": "2.30",
            "cost_price": "1.10",
            "opening_stock": "40",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    product = resp.json()
    assert product["sku"] == "DRK-900"

    movements = await client.get(
        "/api/v1/inventory/movements",
        params={"product_id": product["id"]},
        headers=headers,
    )
    items = movements.json()["items"]
    assert len(items) == 1
    assert items[0]["movement_type"] == "initial"
    assert Decimal(items[0]["quantity"]) == Decimal("40.000")


async def test_duplicate_sku_and_barcode_are_rejected(client: AsyncClient):
    headers = await owner(client)
    base = {"name": "Thing", "sku": "DRK-001", "price": "1.00"}

    sku_clash = await client.post("/api/v1/catalog/products", json=base, headers=headers)
    assert sku_clash.status_code == 409
    assert sku_clash.json()["code"] == "sku_taken"

    barcode_clash = await client.post(
        "/api/v1/catalog/products",
        json={**base, "sku": "NEW-1", "barcode": "5449000000996"},
        headers=headers,
    )
    assert barcode_clash.status_code == 409
    assert barcode_clash.json()["code"] == "barcode_taken"


async def test_deleting_a_product_keeps_it_off_the_grid_but_preserves_history(
    client: AsyncClient,
):
    headers = await owner(client)
    cola = await find_product(client, headers, "DRK-001")

    await client.post("/api/v1/shifts/open", json={"opening_float": "0"}, headers=headers)
    sale = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "1"}],
            "payments": [{"method": "cash", "amount": "1.20"}],
        },
        headers=headers,
    )
    order_id = sale.json()["id"]

    deleted = await client.delete(f"/api/v1/catalog/products/{cola['id']}", headers=headers)
    assert deleted.status_code == 200

    grid = await client.get(
        "/api/v1/catalog/products", params={"search": "DRK-001"}, headers=headers
    )
    assert grid.json()["total"] == 0

    # The receipt must still resolve a year later.
    receipt = await client.get(f"/api/v1/orders/{order_id}/receipt", headers=headers)
    assert receipt.status_code == 200
    assert receipt.json()["order"]["items"][0]["product_name"] == "Cola 330ml can"


async def test_category_delete_orphans_products_rather_than_cascading(
    client: AsyncClient,
):
    headers = await owner(client)
    categories = (await client.get("/api/v1/catalog/categories", headers=headers)).json()
    drinks = next(c for c in categories if c["name"] == "Drinks")

    await client.delete(f"/api/v1/catalog/categories/{drinks['id']}", headers=headers)

    cola = await find_product(client, headers, "DRK-001")
    assert cola["category_id"] is None, "products were deleted along with the category"


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------


async def test_stock_adjustment_updates_level_and_ledger(client: AsyncClient):
    headers = await owner(client)
    cola = await find_product(client, headers, "DRK-001")
    before = Decimal(cola["stock_quantity"])

    resp = await client.post(
        "/api/v1/inventory/adjust",
        json={
            "product_id": cola["id"],
            "movement_type": "purchase",
            "quantity": "48",
            "note": "Delivery",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert Decimal(resp.json()["quantity_after"]) == before + 48

    after = Decimal((await find_product(client, headers, "DRK-001"))["stock_quantity"])
    assert after == before + 48


async def test_stock_count_records_the_difference_not_the_absolute(
    client: AsyncClient,
):
    """The difference is the shrinkage figure; storing only the new count
    would hide the very number a manager is looking for."""
    headers = await owner(client)
    cola = await find_product(client, headers, "DRK-001")  # 240 on hand

    resp = await client.post(
        "/api/v1/inventory/count",
        json={"product_id": cola["id"], "counted_quantity": "232"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["quantity"]) == Decimal("-8.000")
    assert Decimal(body["quantity_after"]) == Decimal("232.000")


async def test_stock_levels_can_filter_to_low_stock(client: AsyncClient):
    headers = await owner(client)
    buns = await find_product(client, headers, "BAK-003")  # 12, threshold 10

    await client.post(
        "/api/v1/inventory/count",
        json={"product_id": buns["id"], "counted_quantity": "3"},
        headers=headers,
    )

    low = await client.get("/api/v1/inventory/levels", params={"low_only": True}, headers=headers)
    skus = [item["sku"] for item in low.json()["items"]]
    assert "BAK-003" in skus


# --------------------------------------------------------------------------
# Employees and RBAC
# --------------------------------------------------------------------------


async def test_owner_can_create_a_cashier(client: AsyncClient):
    headers = await owner(client)
    resp = await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Sam Cashier",
            "email": "sam@corner.example",
            "password": "another-good-passphrase",
            "role": "cashier",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "cashier"
    # The permission set is returned so the UI can explain what they can do.
    assert "order.create" in body["permissions"]
    assert "billing.manage" not in body["permissions"]


async def test_a_manager_cannot_create_an_owner(client: AsyncClient):
    """USER_CREATE without this check is a privilege-escalation button."""
    headers = await owner(client)
    await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Mo Manager",
            "email": "mo@corner.example",
            "password": "another-good-passphrase",
            "role": "manager",
        },
        headers=headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "mo@corner.example",
            "password": "another-good-passphrase",
            "tenant_slug": "corner",
        },
    )
    manager_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Sneaky Owner",
            "email": "sneak@corner.example",
            "password": "another-good-passphrase",
            "role": "owner",
        },
        headers=manager_headers,
    )
    assert resp.status_code == 403


async def test_platform_role_cannot_be_assigned_from_a_shop(client: AsyncClient):
    headers = await owner(client)
    resp = await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Root",
            "email": "root@corner.example",
            "password": "another-good-passphrase",
            "role": "super_admin",
        },
        headers=headers,
    )
    assert resp.status_code == 422


async def test_deactivating_an_employee_revokes_their_sessions_now(
    client: AsyncClient,
):
    """Not "when their token expires" -- an employee walked out means access
    stops immediately."""
    headers = await owner(client)
    created = await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Sam Cashier",
            "email": "sam@corner.example",
            "password": "another-good-passphrase",
            "role": "cashier",
        },
        headers=headers,
    )
    user_id = created.json()["id"]

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "sam@corner.example",
            "password": "another-good-passphrase",
            "tenant_slug": "corner",
        },
    )
    tokens = login.json()

    await client.patch(f"/api/v1/employees/{user_id}", json={"is_active": False}, headers=headers)

    # Access token is rejected because the DB says inactive...
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 401

    # ...and they cannot mint a new one.
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 401


async def test_you_cannot_edit_your_own_role(client: AsyncClient):
    headers = await owner(client)
    me = await client.get("/api/v1/auth/me", headers=headers)
    my_id = me.json()["user"]["id"]

    resp = await client.patch(
        f"/api/v1/employees/{my_id}", json={"role": "cashier"}, headers=headers
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "self_edit_blocked"


async def test_cashier_cannot_reach_the_admin_endpoints(client: AsyncClient):
    headers = await owner(client)
    await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Sam Cashier",
            "email": "sam@corner.example",
            "password": "another-good-passphrase",
            "role": "cashier",
        },
        headers=headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "sam@corner.example",
            "password": "another-good-passphrase",
            "tenant_slug": "corner",
        },
    )
    cashier = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for method, path, body in [
        ("post", "/api/v1/catalog/products", {"name": "x", "sku": "x", "price": "1"}),
        ("get", "/api/v1/employees", None),
        ("get", "/api/v1/analytics/dashboard", None),
        (
            "post",
            "/api/v1/inventory/adjust",
            {
                "product_id": str(login.json() and "00000000-0000-0000-0000-000000000000"),
                "quantity": "1",
            },
        ),
    ]:
        resp = await getattr(client, method)(
            path, headers=cashier, **({"json": body} if body else {})
        )
        assert resp.status_code == 403, f"{method} {path} returned {resp.status_code}"


# --------------------------------------------------------------------------
# Plan quotas
# --------------------------------------------------------------------------


async def test_basic_plan_caps_staff_accounts(client: AsyncClient):
    """The plan limits have existed since Step 1 and enforced nothing."""
    headers = await owner(client, seed=False)

    # Basic allows 3 users; the owner is already one of them.
    for index in range(2):
        resp = await client.post(
            "/api/v1/employees",
            json={
                "full_name": f"Staff {index}",
                "email": f"staff{index}@corner.example",
                "password": "another-good-passphrase",
                "role": "cashier",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    over = await client.post(
        "/api/v1/employees",
        json={
            "full_name": "One Too Many",
            "email": "extra@corner.example",
            "password": "another-good-passphrase",
            "role": "cashier",
        },
        headers=headers,
    )
    assert over.status_code == 402
    assert over.json()["code"] == "quota_exceeded"
    assert over.json()["details"]["limit"] == 3


async def test_usage_summary_reports_against_limits(client: AsyncClient):
    headers = await owner(client)
    resp = await client.get("/api/v1/analytics/usage", headers=headers)
    body = resp.json()
    assert body["plan_name"] == "Basic"
    assert body["products"]["limit"] == 500
    assert body["products"]["used"] == 16
    assert body["users"]["used"] == 1


# --------------------------------------------------------------------------
# Analytics
# --------------------------------------------------------------------------


async def test_dashboard_reflects_actual_trading(client: AsyncClient):
    headers = await owner(client)
    cola = await find_product(client, headers, "DRK-001")
    await client.post("/api/v1/shifts/open", json={"opening_float": "0"}, headers=headers)

    for _ in range(3):
        await client.post(
            "/api/v1/orders",
            json={
                "items": [{"product_id": cola["id"], "quantity": "2"}],
                "payments": [{"method": "cash", "amount": "2.40"}],
            },
            headers=headers,
        )

    resp = await client.get("/api/v1/analytics/dashboard", headers=headers)
    body = resp.json()
    assert body["orders_today"] == 3
    assert Decimal(body["revenue_today"]) == Decimal("7.20")
    assert Decimal(body["average_basket"]) == Decimal("2.40")
    # Cola costs 0.65 and sells for 1.20 -> 0.55 margin on 6 units.
    assert Decimal(body["gross_margin_today"]) == Decimal("3.30")
    assert body["active_shifts"] == 1


async def test_revenue_series_fills_in_quiet_days(client: AsyncClient):
    """A chart that omits empty days compresses a quiet week and reads as
    steady trading."""
    headers = await owner(client)
    resp = await client.get("/api/v1/analytics/revenue", params={"days": 14}, headers=headers)
    series = resp.json()
    assert len(series) == 14
    assert all("day" in point for point in series)
    days = [point["day"] for point in series]
    assert days == sorted(days)


async def test_top_products_ranks_by_revenue(client: AsyncClient):
    headers = await owner(client)
    cola = await find_product(client, headers, "DRK-001")
    nuts = await find_product(client, headers, "SNK-003")
    await client.post("/api/v1/shifts/open", json={"opening_float": "0"}, headers=headers)

    await client.post(
        "/api/v1/orders",
        json={
            "items": [
                {"product_id": cola["id"], "quantity": "2"},
                {"product_id": nuts["id"], "quantity": "5"},
            ],
            "payments": [{"method": "cash", "amount": "25.40"}],
        },
        headers=headers,
    )

    resp = await client.get("/api/v1/analytics/top-products", headers=headers)
    top = resp.json()
    assert top[0]["sku"] == "SNK-003"  # 23.00 beats 2.40
    assert Decimal(top[0]["revenue"]) == Decimal("23.00")


async def test_low_stock_endpoint_lists_items_under_threshold(client: AsyncClient):
    headers = await owner(client)
    buns = await find_product(client, headers, "BAK-003")
    await client.post(
        "/api/v1/inventory/count",
        json={"product_id": buns["id"], "counted_quantity": "2"},
        headers=headers,
    )

    resp = await client.get("/api/v1/analytics/low-stock", headers=headers)
    assert any(item["sku"] == "BAK-003" for item in resp.json())


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


async def test_report_request_is_queued_not_rendered_inline(client: AsyncClient):
    headers = await owner(client)
    resp = await client.post(
        "/api/v1/reports",
        json={
            "report_type": "sales_summary",
            "export_format": "csv",
            "date_from": str(date.today()),
            "date_to": str(date.today()),
        },
        headers=headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    # Redis is not running in the test environment, so queueing fails and the
    # job is marked rather than left pending forever -- which is exactly the
    # behaviour worth pinning.
    assert body["status"] in {"pending", "failed"}
    assert body["is_downloadable"] is False


async def test_report_date_range_is_validated(client: AsyncClient):
    headers = await owner(client)
    backwards = await client.post(
        "/api/v1/reports",
        json={
            "report_type": "tax",
            "date_from": "2026-06-01",
            "date_to": "2026-01-01",
        },
        headers=headers,
    )
    assert backwards.status_code == 422

    too_wide = await client.post(
        "/api/v1/reports",
        json={
            "report_type": "tax",
            "date_from": "2020-01-01",
            "date_to": "2026-01-01",
        },
        headers=headers,
    )
    assert too_wide.status_code == 422


async def test_downloading_an_unfinished_report_is_refused(client: AsyncClient):
    headers = await owner(client)
    queued = await client.post(
        "/api/v1/reports",
        json={
            "report_type": "inventory",
            "date_from": str(date.today()),
            "date_to": str(date.today()),
        },
        headers=headers,
    )
    job_id = queued.json()["id"]

    resp = await client.get(f"/api/v1/reports/{job_id}/download", headers=headers)
    assert resp.status_code in {400, 404}


async def test_product_list_exposes_cost_only_to_privileged_roles(client: AsyncClient):
    """Margin is owner data.

    The list endpoint feeds both the POS grid and the admin catalog table, so
    it has to answer differently for the two audiences -- a cashier must never
    receive what the shop pays, and withholding it in the UI is not the same
    as withholding it from the response.
    """
    headers = await owner(client)

    as_owner = await client.get(
        "/api/v1/catalog/products", params={"search": "DRK-001"}, headers=headers
    )
    row = as_owner.json()["items"][0]
    assert Decimal(row["cost_price"]) == Decimal("0.65")
    assert row["category_name"] == "Drinks"

    await client.post(
        "/api/v1/employees",
        json={
            "full_name": "Sam Cashier",
            "email": "sam@corner.example",
            "password": "another-good-passphrase",
            "role": "cashier",
        },
        headers=headers,
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "sam@corner.example",
            "password": "another-good-passphrase",
            "tenant_slug": "corner",
        },
    )
    cashier = {"Authorization": f"Bearer {login.json()['access_token']}"}

    as_cashier = await client.get(
        "/api/v1/catalog/products", params={"search": "DRK-001"}, headers=cashier
    )
    cashier_row = as_cashier.json()["items"][0]
    assert cashier_row["cost_price"] is None, "cost price leaked to a cashier"
    # The rest of the row still works -- they need price and stock to sell.
    assert Decimal(cashier_row["price"]) == Decimal("1.20")
    assert cashier_row["stock_quantity"] is not None
