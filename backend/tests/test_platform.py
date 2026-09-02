"""Super admin panel: cross-tenant metrics, tenant control, plan management."""

from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import text

from app.db.seed import seed_super_admin
from app.db.session import engine

PLATFORM_EMAIL = "root@saas-pos.example"
PLATFORM_PASSWORD = "platform-operator-passphrase"

SHOP = {
    "shop_name": "Corner Store",
    "slug": "corner",
    "owner_name": "Dana Owner",
    "email": "dana@corner.example",
    "password": "correct-horse-battery",
    "currency": "USD",
    "country_code": "US",
    "plan_code": "basic",
}


async def platform_headers(client: AsyncClient) -> dict[str, str]:
    await seed_super_admin()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": PLATFORM_EMAIL, "password": PLATFORM_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def make_shop(client: AsyncClient, **overrides) -> dict:
    payload = {**SHOP, **overrides}
    resp = await client.post("/api/v1/auth/signup", json=payload)
    assert resp.status_code == 201, resp.text
    return payload


async def shop_headers(client: AsyncClient, payload: dict) -> dict[str, str]:
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
            "tenant_slug": payload["slug"],
        },
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


async def test_shop_owner_cannot_reach_the_platform_api(client: AsyncClient):
    """A shop owner is the most privileged tenant role and still has no
    business here. This is the boundary the whole panel rests on."""
    payload = await make_shop(client)
    headers = await shop_headers(client, payload)

    for path in [
        "/api/v1/platform/metrics",
        "/api/v1/platform/tenants",
        "/api/v1/platform/plans",
        "/api/v1/platform/mrr",
    ]:
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 403, f"{path} returned {resp.status_code}"


async def test_platform_endpoints_reject_anonymous_callers(client: AsyncClient):
    resp = await client.get("/api/v1/platform/metrics")
    assert resp.status_code == 401


async def test_platform_admin_signs_in_without_a_shop_context(client: AsyncClient):
    """Platform staff live in the NULL-tenant namespace, so they authenticate
    on the bare API host with no slug."""
    headers = await platform_headers(client)
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["role"] == "super_admin"
    assert body["user"]["tenant_id"] is None
    assert "platform.tenant.manage" in body["permissions"]
    # Platform staff hold no shop permissions at all.
    assert "order.create" not in body["permissions"]


async def test_platform_admin_cannot_use_shop_endpoints(client: AsyncClient):
    """The escape hatch runs one way: a platform admin can read across shops
    but is not a member of any, so shop-scoped routes refuse them."""
    headers = await platform_headers(client)
    resp = await client.get("/api/v1/analytics/dashboard", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


async def test_metrics_counts_tenants_across_the_platform(client: AsyncClient):
    await make_shop(client)
    await make_shop(client, slug="other", email="sam@other.example", shop_name="Other")
    headers = await platform_headers(client)

    resp = await client.get("/api/v1/platform/metrics", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_tenants"] == 2
    assert body["trialing_tenants"] == 2
    # Two owners; platform staff are not counted as tenant users.
    assert body["total_users"] == 2


async def test_trials_are_pipeline_not_mrr(client: AsyncClient):
    """Counting trials as revenue is how a SaaS dashboard flatters itself."""
    await make_shop(client)
    headers = await platform_headers(client)

    body = (await client.get("/api/v1/platform/metrics", headers=headers)).json()
    assert Decimal(body["mrr"]) == Decimal("0.00")
    assert Decimal(body["trial_pipeline_mrr"]) == Decimal("19.00")


async def test_mrr_normalises_yearly_plans_to_a_monthly_figure(client: AsyncClient):
    await make_shop(client)
    headers = await platform_headers(client)

    tenants = (await client.get("/api/v1/platform/tenants", headers=headers)).json()
    tenant_id = tenants["items"][0]["id"]
    plans = (await client.get("/api/v1/platform/plans", headers=headers)).json()
    enterprise = next(p for p in plans if p["code"] == "enterprise")

    # 1490/year normalises to 124.17/month. `activate` converts the trial --
    # without it the shop keeps trialing and contributes nothing, which is the
    # point: assigning a plan must not start charging someone by accident.
    resp = await client.patch(
        f"/api/v1/platform/tenants/{tenant_id}/plan",
        json={
            "plan_id": enterprise["id"],
            "billing_cycle": "yearly",
            "activate": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200

    body = (await client.get("/api/v1/platform/metrics", headers=headers)).json()
    assert Decimal(body["mrr"]) == Decimal("124.17")
    assert Decimal(body["arr"]) == Decimal("1490.04")


async def test_mrr_series_returns_one_point_per_month(client: AsyncClient):
    headers = await platform_headers(client)
    resp = await client.get("/api/v1/platform/mrr", params={"months": 6}, headers=headers)
    assert resp.status_code == 200
    points = resp.json()
    assert len(points) == 6
    months = [point["month"] for point in points]
    assert months == sorted(months)


# ---------------------------------------------------------------------------
# Tenant management
# ---------------------------------------------------------------------------


async def test_tenant_list_shows_plan_and_usage(client: AsyncClient):
    await make_shop(client)
    headers = await platform_headers(client)

    resp = await client.get("/api/v1/platform/tenants", headers=headers)
    row = resp.json()["items"][0]
    assert row["slug"] == "corner"
    assert row["plan_code"] == "basic"
    assert row["subscription_status"] == "trialing"
    assert row["user_count"] == 1
    assert row["orders_last_30_days"] == 0


async def test_tenant_search_filters_by_name_and_slug(client: AsyncClient):
    await make_shop(client)
    await make_shop(client, slug="bakery", email="pat@bakery.example", shop_name="Village Bakery")
    headers = await platform_headers(client)

    resp = await client.get(
        "/api/v1/platform/tenants", params={"search": "bakery"}, headers=headers
    )
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["slug"] == "bakery"


async def test_blocking_a_shop_cuts_it_off_immediately(client: AsyncClient):
    """The whole point of the block button.

    Suspension must take effect on the next request, not whenever the shop's
    tokens happen to expire -- and an already-open till must stop trading too.
    """
    payload = await make_shop(client)
    shop = await shop_headers(client, payload)
    admin = await platform_headers(client)

    assert (await client.get("/api/v1/auth/me", headers=shop)).status_code == 200

    tenants = (await client.get("/api/v1/platform/tenants", headers=admin)).json()
    tenant_id = tenants["items"][0]["id"]

    blocked = await client.patch(
        f"/api/v1/platform/tenants/{tenant_id}/status",
        json={"status": "suspended", "reason": "Payment failed"},
        headers=admin,
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "suspended"

    # The existing access token is now useless for shop-scoped work.
    resp = await client.get("/api/v1/analytics/dashboard", headers=shop)
    assert resp.status_code == 403
    assert resp.json()["code"] == "tenant_inactive"
    assert "Payment failed" in resp.json()["message"]

    # And they cannot sign in again to get a fresh one.
    relogin = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
            "tenant_slug": payload["slug"],
        },
    )
    assert relogin.status_code == 403
    assert relogin.json()["code"] == "tenant_inactive"


async def test_unblocking_restores_access(client: AsyncClient):
    payload = await make_shop(client)
    admin = await platform_headers(client)
    tenants = (await client.get("/api/v1/platform/tenants", headers=admin)).json()
    tenant_id = tenants["items"][0]["id"]

    await client.patch(
        f"/api/v1/platform/tenants/{tenant_id}/status",
        json={"status": "suspended", "reason": "Payment failed"},
        headers=admin,
    )
    restored = await client.patch(
        f"/api/v1/platform/tenants/{tenant_id}/status",
        json={"status": "active"},
        headers=admin,
    )
    assert restored.status_code == 200
    assert restored.json()["blocked_reason"] is None

    shop = await shop_headers(client, payload)
    assert (await client.get("/api/v1/auth/me", headers=shop)).status_code == 200


async def test_platform_can_create_a_shop_for_a_customer(client: AsyncClient):
    """Sales-assisted onboarding produces a shop identical to a self-signup."""
    headers = await platform_headers(client)
    resp = await client.post(
        "/api/v1/platform/tenants",
        json={
            "shop_name": "Assisted Shop",
            "slug": "assisted",
            "owner_name": "Ray Owner",
            "email": "ray@assisted.example",
            "password": "correct-horse-battery",
            "plan_code": "pro",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["plan_code"] == "pro"

    # The owner can sign in and already has a branch, exactly like a signup.
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "ray@assisted.example",
            "password": "correct-horse-battery",
            "tenant_slug": "assisted",
        },
    )
    assert login.status_code == 200
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.json()["user"]["branch_id"] is not None


async def test_downgrading_a_plan_never_deletes_the_shops_data(client: AsyncClient):
    """A downgrade blocks further additions; it must not silently bin the
    products or staff that no longer fit."""
    payload = await make_shop(client, plan_code="enterprise")
    shop = await shop_headers(client, payload)
    admin = await platform_headers(client)

    for index in range(4):
        created = await client.post(
            "/api/v1/employees",
            json={
                "full_name": f"Staff {index}",
                "email": f"staff{index}@corner.example",
                "password": "another-good-passphrase",
                "role": "cashier",
            },
            headers=shop,
        )
        assert created.status_code == 201, created.text

    tenants = (await client.get("/api/v1/platform/tenants", headers=admin)).json()
    tenant_id = tenants["items"][0]["id"]
    plans = (await client.get("/api/v1/platform/plans", headers=admin)).json()
    basic = next(p for p in plans if p["code"] == "basic")  # max_users = 3

    await client.patch(
        f"/api/v1/platform/tenants/{tenant_id}/plan",
        json={"plan_id": basic["id"]},
        headers=admin,
    )

    # All five accounts survive...
    staff = await client.get("/api/v1/employees", headers=shop)
    assert staff.json()["total"] == 5

    # ...but the sixth is refused until they are back under the limit.
    over = await client.post(
        "/api/v1/employees",
        json={
            "full_name": "One Too Many",
            "email": "extra@corner.example",
            "password": "another-good-passphrase",
            "role": "cashier",
        },
        headers=shop,
    )
    assert over.status_code == 402
    assert over.json()["code"] == "quota_exceeded"


async def test_closing_a_shop_retains_its_trading_history(client: AsyncClient):
    await make_shop(client)
    admin = await platform_headers(client)
    tenants = (await client.get("/api/v1/platform/tenants", headers=admin)).json()
    tenant_id = tenants["items"][0]["id"]

    resp = await client.delete(f"/api/v1/platform/tenants/{tenant_id}", headers=admin)
    assert resp.status_code == 200

    # Gone from the operator's list...
    listing = await client.get("/api/v1/platform/tenants", headers=admin)
    assert listing.json()["total"] == 0

    # ...but the row and its history are still on disk.
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        row = (
            await conn.execute(
                text("SELECT status, deleted_at FROM tenants WHERE id = :id"),
                {"id": tenant_id},
            )
        ).one()
    assert row[0] == "CANCELLED"
    assert row[1] is not None


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


async def test_plan_list_reports_subscribers_and_mrr(client: AsyncClient):
    await make_shop(client)
    headers = await platform_headers(client)

    plans = (await client.get("/api/v1/platform/plans", headers=headers)).json()
    basic = next(p for p in plans if p["code"] == "basic")
    assert basic["subscriber_count"] == 1
    # Trialing, so it contributes no MRR yet.
    assert Decimal(basic["mrr"]) == Decimal("0.00")


async def test_creating_a_plan_with_a_duplicate_code_is_refused(client: AsyncClient):
    headers = await platform_headers(client)
    resp = await client.post(
        "/api/v1/platform/plans",
        json={
            "code": "basic",
            "name": "Basic Again",
            "price_monthly": "9.00",
            "price_yearly": "90.00",
        },
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "code_taken"


async def test_raising_a_list_price_does_not_rebill_existing_shops(
    client: AsyncClient,
):
    """Subscriptions freeze their amount at signup precisely so an operator
    editing a tier cannot silently increase what a shop already pays."""
    await make_shop(client)
    headers = await platform_headers(client)

    plans = (await client.get("/api/v1/platform/plans", headers=headers)).json()
    basic = next(p for p in plans if p["code"] == "basic")

    await client.patch(
        f"/api/v1/platform/plans/{basic['id']}",
        json={"price_monthly": "49.00"},
        headers=headers,
    )

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        amount = await conn.scalar(text("SELECT unit_amount FROM subscriptions"))
    assert Decimal(amount) == Decimal("19.00"), "an existing shop was re-priced"


async def test_retiring_a_plan_leaves_its_subscribers_alone(client: AsyncClient):
    await make_shop(client)
    headers = await platform_headers(client)
    plans = (await client.get("/api/v1/platform/plans", headers=headers)).json()
    basic = next(p for p in plans if p["code"] == "basic")

    resp = await client.delete(f"/api/v1/platform/plans/{basic['id']}", headers=headers)
    assert resp.status_code == 200
    assert "1 existing shop stays" in resp.json()["message"]

    after = (await client.get("/api/v1/platform/plans", headers=headers)).json()
    retired = next(p for p in after if p["code"] == "basic")
    assert retired["is_active"] is False
    assert retired["subscriber_count"] == 1


async def test_new_plan_becomes_available_for_signup(client: AsyncClient):
    headers = await platform_headers(client)
    created = await client.post(
        "/api/v1/platform/plans",
        json={
            "code": "starter",
            "name": "Starter",
            "price_monthly": "9.00",
            "price_yearly": "90.00",
            "trial_days": 7,
            "max_users": 2,
            "max_products": 100,
        },
        headers=headers,
    )
    assert created.status_code == 201

    signup = await client.post("/api/v1/auth/signup", json={**SHOP, "plan_code": "starter"})
    assert signup.status_code == 201

    tenants = (await client.get("/api/v1/platform/tenants", headers=headers)).json()
    assert tenants["items"][0]["plan_code"] == "starter"


async def test_changing_plan_does_not_end_a_trial_by_accident(client: AsyncClient):
    """Fixing a mis-selected tier for a shop still in its trial must not bill
    them a fortnight early."""
    await make_shop(client)
    headers = await platform_headers(client)

    tenants = (await client.get("/api/v1/platform/tenants", headers=headers)).json()
    tenant_id = tenants["items"][0]["id"]
    plans = (await client.get("/api/v1/platform/plans", headers=headers)).json()
    pro = next(p for p in plans if p["code"] == "pro")

    resp = await client.patch(
        f"/api/v1/platform/tenants/{tenant_id}/plan",
        json={"plan_id": pro["id"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["plan_code"] == "pro"
    assert resp.json()["subscription_status"] == "trialing"

    metrics = (await client.get("/api/v1/platform/metrics", headers=headers)).json()
    assert Decimal(metrics["mrr"]) == Decimal("0.00")
    assert Decimal(metrics["trial_pipeline_mrr"]) == Decimal("49.00")


async def test_activating_moves_a_shop_from_pipeline_into_mrr(client: AsyncClient):
    await make_shop(client)
    headers = await platform_headers(client)

    tenants = (await client.get("/api/v1/platform/tenants", headers=headers)).json()
    tenant_id = tenants["items"][0]["id"]
    plans = (await client.get("/api/v1/platform/plans", headers=headers)).json()
    pro = next(p for p in plans if p["code"] == "pro")

    resp = await client.patch(
        f"/api/v1/platform/tenants/{tenant_id}/plan",
        json={"plan_id": pro["id"], "activate": True},
        headers=headers,
    )
    assert resp.json()["subscription_status"] == "active"
    assert resp.json()["status"] == "active"

    metrics = (await client.get("/api/v1/platform/metrics", headers=headers)).json()
    assert Decimal(metrics["mrr"]) == Decimal("49.00")
    assert Decimal(metrics["trial_pipeline_mrr"]) == Decimal("0.00")
    assert metrics["active_tenants"] == 1
    assert metrics["trialing_tenants"] == 0
