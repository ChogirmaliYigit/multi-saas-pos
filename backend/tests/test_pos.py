"""POS checkout, against a real database."""

from __future__ import annotations

import asyncio
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
    "plan_code": "basic",
}


async def bootstrap(client: AsyncClient) -> dict[str, str]:
    """A shop with a seeded catalog and an open till."""
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    await seed_demo("corner")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"], "tenant_slug": "corner"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/shifts/open", json={"opening_float": "100.00"}, headers=headers)
    return headers


async def product_by_sku(client: AsyncClient, headers: dict, sku: str) -> dict:
    resp = await client.get("/api/v1/catalog/products", params={"search": sku}, headers=headers)
    return resp.json()["items"][0]


async def test_barcode_lookup_resolves_a_scan(client: AsyncClient):
    headers = await bootstrap(client)
    resp = await client.get(
        "/api/v1/catalog/lookup", params={"code": "5449000000996"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["product"]["name"] == "Cola 330ml can"
    assert body["matched_on"] == "barcode"
    assert Decimal(body["pack_size"]) == 1


async def test_pack_barcode_adds_the_whole_case(client: AsyncClient):
    """Scanning a carton must add 24, not 1 -- the entire point of the
    product_barcodes table."""
    headers = await bootstrap(client)
    resp = await client.get(
        "/api/v1/catalog/lookup", params={"code": "15449000000993"}, headers=headers
    )
    body = resp.json()
    assert body["matched_on"] == "pack_barcode"
    assert Decimal(body["pack_size"]) == 24


async def test_lookup_falls_back_to_sku(client: AsyncClient):
    headers = await bootstrap(client)
    resp = await client.get("/api/v1/catalog/lookup", params={"code": "BAK-002"}, headers=headers)
    assert resp.json()["matched_on"] == "sku"


async def test_unknown_code_is_a_clean_404(client: AsyncClient):
    headers = await bootstrap(client)
    resp = await client.get(
        "/api/v1/catalog/lookup", params={"code": "0000000000000"}, headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "product_not_found"


async def test_checkout_creates_order_and_moves_stock(client: AsyncClient):
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")
    before = Decimal(cola["stock_quantity"])

    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "3"}],
            "payments": [{"method": "cash", "amount": "5.00", "tendered_amount": "5.00"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()

    assert Decimal(order["total"]) == Decimal("3.60")  # 1.20 * 3
    assert Decimal(order["change_due"]) == Decimal("1.40")
    assert order["order_number"].startswith("MAIN-")
    assert len(order["items"]) == 1

    after = Decimal((await product_by_sku(client, headers, "DRK-001"))["stock_quantity"])
    assert after == before - 3

    # The ledger records it too, so stock is reconstructable.
    # This raw connection has no tenant bound, so RLS would (correctly) hide
    # every row -- read it as the platform instead.
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        movement = (
            await conn.execute(
                text(
                    "SELECT quantity, movement_type, reference_type FROM stock_movements "
                    "WHERE reference_id = :oid"
                ),
                {"oid": order["id"]},
            )
        ).one()
    assert movement[0] == Decimal("-3.000")
    assert movement[2] == "order"


async def test_client_cannot_name_its_own_price(client: AsyncClient):
    """The cart payload says *what*, never *how much*. A tampered price must
    be ignored in favour of the shelf price."""
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")

    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "1", "unit_price": "0.01"}],
            "payments": [{"method": "cash", "amount": "1.20"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert Decimal(resp.json()["total"]) == Decimal("1.20")


async def test_underpayment_is_rejected(client: AsyncClient):
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")
    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "3"}],
            "payments": [{"method": "cash", "amount": "1.00"}],
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "payment_mismatch"


async def test_split_payment_across_cash_and_card(client: AsyncClient):
    headers = await bootstrap(client)
    nuts = await product_by_sku(client, headers, "SNK-003")
    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": nuts["id"], "quantity": "2"}],
            "payments": [
                {"method": "cash", "amount": "5.00"},
                {"method": "card", "amount": "4.20", "card_last4": "4242"},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    order = resp.json()
    assert Decimal(order["total"]) == Decimal("9.20")
    assert len(order["payments"]) == 2


async def test_selling_more_than_stock_is_refused(client: AsyncClient):
    headers = await bootstrap(client)
    buns = await product_by_sku(client, headers, "BAK-003")  # 12 in stock
    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": buns["id"], "quantity": "50"}],
            "payments": [{"method": "cash", "amount": "200.00"}],
        },
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "insufficient_stock"


async def test_failed_sale_leaves_no_trace(client: AsyncClient):
    """The transaction boundary: a sale that fails partway must not consume a
    receipt number, move stock, or leave an orphan order."""
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")
    buns = await product_by_sku(client, headers, "BAK-003")
    stock_before = Decimal(cola["stock_quantity"])

    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [
                {"product_id": cola["id"], "quantity": "2"},
                {"product_id": buns["id"], "quantity": "999"},  # fails here
            ],
            "payments": [{"method": "cash", "amount": "5000.00"}],
        },
        headers=headers,
    )
    assert resp.status_code == 409

    after = Decimal((await product_by_sku(client, headers, "DRK-001"))["stock_quantity"])
    assert after == stock_before, "the first line's stock was not rolled back"

    orders = await client.get("/api/v1/orders", headers=headers)
    assert orders.json()["total"] == 0


async def test_idempotency_key_prevents_a_double_charge(client: AsyncClient):
    """A tablet that retries after a dropped connection must not sell twice."""
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")
    payload = {
        "items": [{"product_id": cola["id"], "quantity": "1"}],
        "payments": [{"method": "cash", "amount": "1.20"}],
        "idempotency_key": "terminal-1-attempt-abc123",
    }

    first = await client.post("/api/v1/orders", json=payload, headers=headers)
    second = await client.post("/api/v1/orders", json=payload, headers=headers)

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["order_number"] == second.json()["order_number"]

    listing = await client.get("/api/v1/orders", headers=headers)
    assert listing.json()["total"] == 1, "the retry created a second sale"


async def test_receipt_numbers_are_sequential_per_branch_and_day(client: AsyncClient):
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")
    numbers = []
    for _ in range(3):
        resp = await client.post(
            "/api/v1/orders",
            json={
                "items": [{"product_id": cola["id"], "quantity": "1"}],
                "payments": [{"method": "cash", "amount": "1.20"}],
            },
            headers=headers,
        )
        numbers.append(resp.json()["order_number"])

    sequences = [int(n.rsplit("-", 1)[1]) for n in numbers]
    assert sequences == [1, 2, 3]


async def test_checkout_without_an_open_shift_is_refused(client: AsyncClient):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    await seed_demo("corner")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"], "tenant_slug": "corner"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    cola = await product_by_sku(client, headers, "DRK-001")

    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "1"}],
            "payments": [{"method": "cash", "amount": "1.20"}],
        },
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_open_shift"


async def test_inclusive_tax_reaches_the_receipt(client: AsyncClient):
    """Cola is VAT 20% inclusive at 1.20: the customer pays 1.20 and the
    receipt must show 0.20 of tax inside it, not 0.24 added on top."""
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")
    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "1"}],
            "payments": [{"method": "cash", "amount": "1.20"}],
        },
        headers=headers,
    )
    order = resp.json()
    assert Decimal(order["total"]) == Decimal("1.20")
    assert Decimal(order["tax_total"]) == Decimal("0.20")

    receipt = await client.get(f"/api/v1/orders/{order['id']}/receipt", headers=headers)
    assert receipt.status_code == 200
    body = receipt.json()
    assert body["shop"]["name"] == "Corner Store"
    assert body["cashier_name"] == "Dana Owner"
    assert Decimal(body["order"]["tax_total"]) == Decimal("0.20")


async def test_shift_close_reconciles_the_drawer(client: AsyncClient):
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")
    await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "5"}],  # 6.00
            "payments": [{"method": "cash", "amount": "10.00", "tendered_amount": "10.00"}],
        },
        headers=headers,
    )

    summary = await client.get("/api/v1/shifts/current/summary", headers=headers)
    body = summary.json()
    assert body["order_count"] == 1
    assert Decimal(body["cash_sales"]) == Decimal("10.00")
    # 100 float + 10 taken - 4 change = 106
    assert Decimal(body["shift"]["expected_cash"]) == Decimal("106.00")

    closed = await client.post(
        "/api/v1/shifts/current/close",
        json={"counted_cash": "104.00"},
        headers=headers,
    )
    assert closed.status_code == 200
    # Two dollars short: exactly the number a manager needs to see.
    assert Decimal(closed.json()["cash_difference"]) == Decimal("-2.00")
    assert closed.json()["status"] == "closed"


async def test_two_terminals_cannot_both_sell_the_last_unit(client: AsyncClient):
    """The concurrency claim, actually exercised.

    Stock is decremented by `UPDATE ... WHERE quantity >= :qty`, so the guard
    is inside the statement the database serialises. A read-then-write would
    let every one of these requests observe "1 in stock" and all succeed,
    leaving stock at -4 and five customers holding the same item.
    """
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        await conn.execute(
            text("UPDATE stock_items SET quantity = 1 WHERE product_id = :pid"),
            {"pid": cola["id"]},
        )

    payload = {
        "items": [{"product_id": cola["id"], "quantity": "1"}],
        "payments": [{"method": "cash", "amount": "1.20"}],
    }
    results = await asyncio.gather(
        *(client.post("/api/v1/orders", json=payload, headers=headers) for _ in range(5)),
        return_exceptions=True,
    )

    statuses = [r.status_code for r in results if not isinstance(r, Exception)]
    assert statuses.count(201) == 1, f"expected exactly one sale, got {statuses}"

    remaining = Decimal((await product_by_sku(client, headers, "DRK-001"))["stock_quantity"])
    assert remaining == 0, f"stock went to {remaining}"


async def test_cashier_cannot_apply_a_discount_without_permission(client: AsyncClient):
    """Discounts are the usual route for shrinkage to leave through the front
    door, so they are a separate permission from ringing up a sale."""
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")

    # Create a cashier and sign in as them.
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        await conn.execute(
            text(
                "INSERT INTO users (id, tenant_id, branch_id, email, full_name, "
                "hashed_password, role, permission_overrides, is_active, "
                "failed_login_count, created_at, updated_at) "
                "SELECT gen_random_uuid(), u.tenant_id, u.branch_id, "
                "'till@corner.example', 'Sam Cashier', u.hashed_password, 'CASHIER', "
                "'{}'::jsonb, true, 0, now(), now() FROM users u "
                "WHERE u.email = 'dana@corner.example'"
            )
        )

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "till@corner.example",
            "password": SIGNUP["password"],
            "tenant_slug": "corner",
        },
    )
    cashier_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    await client.post("/api/v1/shifts/open", json={"opening_float": "0"}, headers=cashier_headers)

    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "1"}],
            "payments": [{"method": "cash", "amount": "1.00"}],
            "discount_type": "percent",
            "discount_value": "50",
        },
        headers=cashier_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["details"]["required"] == ["order.discount"]


async def test_cashier_sees_only_their_own_sales(client: AsyncClient):
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")
    await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "1"}],
            "payments": [{"method": "cash", "amount": "1.20"}],
        },
        headers=headers,
    )

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        await conn.execute(
            text(
                "INSERT INTO users (id, tenant_id, branch_id, email, full_name, "
                "hashed_password, role, permission_overrides, is_active, "
                "failed_login_count, created_at, updated_at) "
                "SELECT gen_random_uuid(), u.tenant_id, u.branch_id, "
                "'till2@corner.example', 'Kim Cashier', u.hashed_password, 'CASHIER', "
                "'{}'::jsonb, true, 0, now(), now() FROM users u "
                "WHERE u.email = 'dana@corner.example'"
            )
        )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "till2@corner.example",
            "password": SIGNUP["password"],
            "tenant_slug": "corner",
        },
    )
    cashier_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listing = await client.get("/api/v1/orders", headers=cashier_headers)
    assert listing.json()["total"] == 0, "cashier saw another user's takings"


async def test_cash_tendered_above_the_total_records_change(client: AsyncClient):
    """A 50.00 note for a 30.00 sale must record 20.00 of change.

    Change is what the receipt prints and what drawer reconciliation depends
    on; deriving it only from over-applied amounts, rather than from the
    tendered note, silently reported zero.
    """
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")

    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "25"}],  # 30.00
            "payments": [{"method": "cash", "amount": "30.00", "tendered_amount": "50.00"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()

    assert Decimal(order["total"]) == Decimal("30.00")
    assert Decimal(order["change_due"]) == Decimal("20.00")
    assert Decimal(order["payments"][0]["tendered_amount"]) == Decimal("50.00")

    # Drawer: 100 float + 50 in - 20 out = 130.
    summary = await client.get("/api/v1/shifts/current/summary", headers=headers)
    assert Decimal(summary.json()["shift"]["expected_cash"]) == Decimal("130.00")


async def test_card_payment_has_no_change(client: AsyncClient):
    headers = await bootstrap(client)
    cola = await product_by_sku(client, headers, "DRK-001")
    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": cola["id"], "quantity": "1"}],
            "payments": [{"method": "card", "amount": "1.20", "card_last4": "4242"}],
        },
        headers=headers,
    )
    order = resp.json()
    assert Decimal(order["change_due"]) == Decimal("0.00")

    summary = await client.get("/api/v1/shifts/current/summary", headers=headers)
    # Card takings must not inflate the cash drawer.
    assert Decimal(summary.json()["shift"]["expected_cash"]) == Decimal("100.00")


async def test_split_cash_and_card_with_change_on_the_cash_part(client: AsyncClient):
    headers = await bootstrap(client)
    nuts = await product_by_sku(client, headers, "SNK-003")  # 4.60 each
    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": nuts["id"], "quantity": "2"}],  # 9.20
            "payments": [
                {"method": "cash", "amount": "5.00", "tendered_amount": "10.00"},
                {"method": "card", "amount": "4.20"},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    order = resp.json()
    assert Decimal(order["total"]) == Decimal("9.20")
    assert Decimal(order["change_due"]) == Decimal("5.00")

    summary = await client.get("/api/v1/shifts/current/summary", headers=headers)
    # 100 float + 10 cash in - 5 change out = 105; the card leg is not cash.
    assert Decimal(summary.json()["shift"]["expected_cash"]) == Decimal("105.00")
