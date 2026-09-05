"""The demo seeder must leave a shop the application can keep trading in."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import text

from app.db.seed_showcase import DEMO_PASSWORD, seed_showcase
from app.db.session import engine

SIGNUP = {
    "shop_name": "Demo Market",
    "slug": "demo",
    "owner_name": "Dilshod Rahimov",
    "email": "admin@demo.joinpay.uz",
    "password": DEMO_PASSWORD,
    "currency": "UZS",
    "country_code": "UZ",
    "plan_code": "pro",
}


async def seeded_owner(client: AsyncClient) -> dict[str, str]:
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    await seed_showcase("demo")
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": SIGNUP["email"],
            "password": SIGNUP["password"],
            "tenant_slug": "demo",
        },
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_a_real_sale_can_follow_the_seeded_history(client: AsyncClient):
    """The regression this file exists for.

    The seeder writes its own receipt numbers. next_order_number counts from
    order_counters, so if the seed does not hand that series over, the first
    genuine checkout restarts at 0001 and collides with a seeded receipt --
    the demo breaks the moment anyone tries to sell something in it.
    """
    headers = await seeded_owner(client)

    products = await client.get(
        "/api/v1/catalog/products", params={"search": "ICH-001"}, headers=headers
    )
    product_id = products.json()["items"][0]["id"]

    await client.post("/api/v1/shifts/open", json={"opening_float": "0"}, headers=headers)
    sale = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": product_id, "quantity": "1"}],
            "payments": [{"method": "cash", "amount": "8000"}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text

    # And it continues the day's series rather than starting a second one.
    number = sale.json()["order_number"]
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        clashes = await conn.scalar(
            text("SELECT count(*) FROM orders WHERE order_number = :n"), {"n": number}
        )
    assert clashes == 1


async def test_seeding_is_idempotent(client: AsyncClient):
    """Running it twice must not double the history."""
    headers = await seeded_owner(client)
    before = (await client.get("/api/v1/orders", headers=headers)).json()["total"]

    await seed_showcase("demo")

    after = (await client.get("/api/v1/orders", headers=headers)).json()["total"]
    assert after == before


async def test_reset_replaces_the_history_rather_than_appending(client: AsyncClient):
    headers = await seeded_owner(client)
    before = (await client.get("/api/v1/orders", headers=headers)).json()["total"]
    assert before > 0

    await seed_showcase("demo", reset=True)

    after = (await client.get("/api/v1/orders", headers=headers)).json()["total"]
    assert after == before  # deterministic, so the same run reproduces exactly


async def test_the_seeded_shop_is_worth_demonstrating(client: AsyncClient):
    """A demo whose dashboard reads zero demonstrates nothing."""
    headers = await seeded_owner(client)

    dashboard = (await client.get("/api/v1/analytics/dashboard", headers=headers)).json()
    assert float(dashboard["revenue_today"]) > 0
    assert dashboard["orders_today"] > 0
    assert dashboard["active_shifts"] > 0
    assert dashboard["low_stock_count"] > 0
    assert dashboard["currency"] == "UZS"

    assert len((await client.get("/api/v1/analytics/revenue", headers=headers)).json()) > 20
    assert len((await client.get("/api/v1/analytics/top-products", headers=headers)).json()) > 0
    # All four payment methods should appear, so the split chart has segments.
    assert len((await client.get("/api/v1/analytics/payments", headers=headers)).json()) == 4


async def test_stock_levels_match_their_own_ledger(client: AsyncClient):
    """Inventory, sales and the movement history have to agree, or the first
    person who checks the demo's arithmetic finds it does not add up."""
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    await seed_showcase("demo")

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        mismatches = await conn.scalar(
            text(
                """
                SELECT count(*) FROM (
                    SELECT si.product_id
                    FROM stock_items si
                    JOIN (
                        SELECT product_id, sum(quantity) AS net
                        FROM stock_movements GROUP BY product_id
                    ) m ON m.product_id = si.product_id
                    WHERE si.quantity <> m.net
                ) AS bad
                """
            )
        )
    assert mismatches == 0
