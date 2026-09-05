"""Refunds. Every assertion here is money leaving a till."""

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
    "plan_code": "basic",
}


async def shop(client: AsyncClient) -> dict[str, str]:
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    await seed_demo("corner")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"], "tenant_slug": "corner"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    await client.post("/api/v1/shifts/open", json={"opening_float": "100.00"}, headers=headers)
    return headers


async def product(client: AsyncClient, headers: dict, sku: str) -> dict:
    resp = await client.get("/api/v1/catalog/products", params={"search": sku}, headers=headers)
    return resp.json()["items"][0]


async def sell(
    client: AsyncClient,
    headers: dict,
    items: list[tuple[str, str]],
    paid: str,
    tendered: str | None = None,
) -> dict:
    """items: [(sku, qty)]"""
    lines = []
    for sku, qty in items:
        p = await product(client, headers, sku)
        lines.append({"product_id": p["id"], "quantity": qty})
    payment = {"method": "cash", "amount": paid}
    if tendered:
        payment["tendered_amount"] = tendered
    resp = await client.post(
        "/api/v1/orders", json={"items": lines, "payments": [payment]}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# The basics
# ---------------------------------------------------------------------------


async def test_full_refund_returns_everything_and_restocks(client: AsyncClient):
    headers = await shop(client)
    before = Decimal((await product(client, headers, "DRK-001"))["stock_quantity"])
    order = await sell(client, headers, [("DRK-001", "3")], "3.60")

    resp = await client.post(
        f"/api/v1/orders/{order['id']}/refund",
        json={"reason": "Customer changed mind"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    refund = resp.json()
    assert Decimal(refund["amount"]) == Decimal("3.60")
    assert refund["restocked"] is True

    after = Decimal((await product(client, headers, "DRK-001"))["stock_quantity"])
    assert after == before, "stock did not come back"

    updated = (await client.get(f"/api/v1/orders/{order['id']}", headers=headers)).json()
    assert updated["status"] == "refunded"
    assert Decimal(updated["refunded_total"]) == Decimal("3.60")
    # The original totals are untouched -- a receipt reprint must still show
    # what the customer originally paid.
    assert Decimal(updated["total"]) == Decimal("3.60")


async def test_partial_refund_of_one_line(client: AsyncClient):
    """The normal case: three items bought, one brought back."""
    headers = await shop(client)
    before = Decimal((await product(client, headers, "DRK-001"))["stock_quantity"])
    order = await sell(client, headers, [("DRK-001", "3")], "3.60")
    item_id = order["items"][0]["id"]

    resp = await client.post(
        f"/api/v1/orders/{order['id']}/refund",
        json={"lines": [{"order_item_id": item_id, "quantity": "1"}]},
        headers=headers,
    )
    assert resp.status_code == 201
    assert Decimal(resp.json()["amount"]) == Decimal("1.20")

    updated = (await client.get(f"/api/v1/orders/{order['id']}", headers=headers)).json()
    assert updated["status"] == "partially_refunded"
    assert Decimal(updated["refunded_total"]) == Decimal("1.20")

    after = Decimal((await product(client, headers, "DRK-001"))["stock_quantity"])
    assert after == before - 2, "only the un-refunded units should stay sold"


async def test_refunding_more_than_was_bought_is_refused(client: AsyncClient):
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "2")], "2.40")
    item_id = order["items"][0]["id"]

    resp = await client.post(
        f"/api/v1/orders/{order['id']}/refund",
        json={"lines": [{"order_item_id": item_id, "quantity": "5"}]},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "refund_exceeds_order"


async def test_two_partial_refunds_cannot_exceed_the_order(client: AsyncClient):
    """The arithmetic has to hold across separate visits, not just one."""
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "3")], "3.60")
    item_id = order["items"][0]["id"]

    for _ in range(3):
        resp = await client.post(
            f"/api/v1/orders/{order['id']}/refund",
            json={"lines": [{"order_item_id": item_id, "quantity": "1"}]},
            headers=headers,
        )
        assert resp.status_code == 201

    # By now the order is fully refunded, so the status guard answers first.
    # "This order is fully refunded" is a more useful message than "you asked
    # for more than remains".
    fourth = await client.post(
        f"/api/v1/orders/{order['id']}/refund",
        json={"lines": [{"order_item_id": item_id, "quantity": "1"}]},
        headers=headers,
    )
    assert fourth.status_code == 409
    assert fourth.json()["code"] == "order_not_refundable"

    updated = (await client.get(f"/api/v1/orders/{order['id']}", headers=headers)).json()
    assert Decimal(updated["refunded_total"]) == Decimal("3.60")
    assert updated["status"] == "refunded"


async def test_client_cannot_name_the_refund_amount(client: AsyncClient):
    """A refund endpoint that trusted a client amount would be a
    cash-withdrawal endpoint."""
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "1")], "1.20")
    item_id = order["items"][0]["id"]

    resp = await client.post(
        f"/api/v1/orders/{order['id']}/refund",
        json={
            "lines": [{"order_item_id": item_id, "quantity": "1"}],
            "amount": "9999.00",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert Decimal(resp.json()["amount"]) == Decimal("1.20")


# ---------------------------------------------------------------------------
# Money and stock
# ---------------------------------------------------------------------------


async def test_cash_refund_reduces_the_drawer(client: AsyncClient):
    """Otherwise the till reconciles short at close by exactly the refund."""
    headers = await shop(client)
    await sell(client, headers, [("DRK-001", "5")], "6.00", tendered="10.00")

    summary = (await client.get("/api/v1/shifts/current/summary", headers=headers)).json()
    # 100 float + 10 in - 4 change = 106
    assert Decimal(summary["shift"]["expected_cash"]) == Decimal("106.00")

    orders = (await client.get("/api/v1/orders", headers=headers)).json()
    order_id = orders["items"][0]["id"]
    await client.post(f"/api/v1/orders/{order_id}/refund", json={}, headers=headers)

    after = (await client.get("/api/v1/shifts/current/summary", headers=headers)).json()
    assert Decimal(after["shift"]["expected_cash"]) == Decimal("100.00")


async def test_refund_without_restock_returns_money_but_not_stock(client: AsyncClient):
    """Damaged goods: the customer gets paid, the item does not go back on
    the shelf."""
    headers = await shop(client)
    before = Decimal((await product(client, headers, "DRK-001"))["stock_quantity"])
    order = await sell(client, headers, [("DRK-001", "2")], "2.40")

    resp = await client.post(
        f"/api/v1/orders/{order['id']}/refund",
        json={"restock": False, "reason": "Damaged"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert Decimal(resp.json()["amount"]) == Decimal("2.40")

    after = Decimal((await product(client, headers, "DRK-001"))["stock_quantity"])
    assert after == before - 2, "damaged stock was put back on the shelf"


async def test_restock_writes_the_ledger(client: AsyncClient):
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "2")], "2.40")
    await client.post(f"/api/v1/orders/{order['id']}/refund", json={}, headers=headers)

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        row = (
            await conn.execute(
                text(
                    "SELECT movement_type, quantity, reference_type FROM stock_movements "
                    "WHERE movement_type = 'RETURN'"
                )
            )
        ).one()
    assert row[0] == "RETURN"
    assert row[1] == Decimal("2.000")
    assert row[2] == "refund"


async def test_refund_defaults_to_how_they_paid(client: AsyncClient):
    """Refunding cash for a card sale is how a till ends up short."""
    headers = await shop(client)
    nuts = await product(client, headers, "SNK-003")
    order = (
        await client.post(
            "/api/v1/orders",
            json={
                "items": [{"product_id": nuts["id"], "quantity": "1"}],
                "payments": [{"method": "card", "amount": "4.60", "card_last4": "4242"}],
            },
            headers=headers,
        )
    ).json()

    resp = await client.post(f"/api/v1/orders/{order['id']}/refund", json={}, headers=headers)
    assert resp.json()["method"] == "card"

    # A card refund must not touch the cash drawer.
    summary = (await client.get("/api/v1/shifts/current/summary", headers=headers)).json()
    assert Decimal(summary["shift"]["expected_cash"]) == Decimal("100.00")


async def test_discounted_line_refunds_what_was_actually_paid(client: AsyncClient):
    """Not the list price. Refunding half a discounted line returns half of
    what the customer handed over."""
    headers = await shop(client)
    cola = await product(client, headers, "DRK-001")
    order = (
        await client.post(
            "/api/v1/orders",
            json={
                "items": [{"product_id": cola["id"], "quantity": "4"}],
                "payments": [{"method": "cash", "amount": "2.40"}],
                "discount_type": "percent",
                "discount_value": "50",
            },
            headers=headers,
        )
    ).json()
    assert Decimal(order["total"]) == Decimal("2.40")  # 4.80 less 50%

    item_id = order["items"][0]["id"]
    resp = await client.post(
        f"/api/v1/orders/{order['id']}/refund",
        json={"lines": [{"order_item_id": item_id, "quantity": "2"}]},
        headers=headers,
    )
    # Half of 2.40, not half of the 4.80 list price.
    assert Decimal(resp.json()["amount"]) == Decimal("1.20")


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


async def test_refund_needs_its_own_permission(client: AsyncClient):
    """A refund is the shortest path from the till to someone's pocket."""
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "1")], "1.20")

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
    await client.post("/api/v1/shifts/open", json={"opening_float": "0"}, headers=cashier)

    resp = await client.post(f"/api/v1/orders/{order['id']}/refund", json={}, headers=cashier)
    assert resp.status_code == 403


async def test_refund_requires_an_open_shift(client: AsyncClient):
    """Money leaving the till has to land in a shift, or the drawer cannot be
    reconciled at close."""
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "1")], "1.20")
    await client.post("/api/v1/shifts/current/close", json={"counted_cash": "0"}, headers=headers)

    resp = await client.post(f"/api/v1/orders/{order['id']}/refund", json={}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "no_open_shift"


async def test_refunding_an_already_refunded_order_is_refused(client: AsyncClient):
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "1")], "1.20")
    await client.post(f"/api/v1/orders/{order['id']}/refund", json={}, headers=headers)

    again = await client.post(f"/api/v1/orders/{order['id']}/refund", json={}, headers=headers)
    assert again.status_code == 409
    assert again.json()["code"] == "order_not_refundable"


async def test_idempotency_key_prevents_a_double_refund(client: AsyncClient):
    """A tablet retrying after a dropped connection must not pay out twice."""
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "2")], "2.40")
    payload = {"idempotency_key": "till-1-refund-abc"}

    first = await client.post(f"/api/v1/orders/{order['id']}/refund", json=payload, headers=headers)
    second = await client.post(
        f"/api/v1/orders/{order['id']}/refund", json=payload, headers=headers
    )

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    updated = (await client.get(f"/api/v1/orders/{order['id']}", headers=headers)).json()
    assert Decimal(updated["refunded_total"]) == Decimal("2.40"), "refunded twice"


async def test_cross_tenant_refund_is_impossible(client: AsyncClient):
    """The tenancy guarantee, on the endpoint that moves money outward."""
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "1")], "1.20")

    await client.post(
        "/api/v1/auth/signup",
        json={**SIGNUP, "slug": "other", "email": "sam@other.example", "shop_name": "Other"},
    )
    other = await client.post(
        "/api/v1/auth/login",
        json={"email": "sam@other.example", "password": SIGNUP["password"], "tenant_slug": "other"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    resp = await client.post(f"/api/v1/orders/{order['id']}/refund", json={}, headers=other_headers)
    assert resp.status_code == 404, "another shop's order was visible"


# ---------------------------------------------------------------------------
# The refund screen
# ---------------------------------------------------------------------------


async def test_refundable_view_shows_per_line_remainders(client: AsyncClient):
    headers = await shop(client)
    order = await sell(client, headers, [("DRK-001", "3"), ("BAK-002", "2")], "6.80")
    cola_line = next(i for i in order["items"] if i["sku"] == "DRK-001")

    await client.post(
        f"/api/v1/orders/{order['id']}/refund",
        json={"lines": [{"order_item_id": cola_line["id"], "quantity": "1"}]},
        headers=headers,
    )

    view = (await client.get(f"/api/v1/orders/{order['id']}/refundable", headers=headers)).json()
    assert view["status"] == "partially_refunded"
    assert Decimal(view["refunded_total"]) == Decimal("1.20")
    assert Decimal(view["refundable_total"]) == Decimal("5.60")

    cola = next(line for line in view["lines"] if line["sku"] == "DRK-001")
    assert Decimal(cola["refunded_quantity"]) == Decimal("1.000")
    assert Decimal(cola["refundable_quantity"]) == Decimal("2.000")
    assert Decimal(cola["refundable_amount"]) == Decimal("2.40")

    assert len(view["refunds"]) == 1
    assert view["refunds"][0]["lines"][0]["product_name"] == "Cola 330ml can"
