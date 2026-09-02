from __future__ import annotations

from httpx import AsyncClient

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


async def signup_and_login(client: AsyncClient, **overrides) -> dict:
    payload = {**SIGNUP, **overrides}
    resp = await client.post("/api/v1/auth/signup", json=payload)
    assert resp.status_code == 201, resp.text
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
            "tenant_slug": payload["slug"],
        },
    )
    assert login.status_code == 200, login.text
    return login.json()


async def test_signup_creates_shop_owner_branch_and_trial(client: AsyncClient):
    resp = await client.post("/api/v1/auth/signup", json=SIGNUP)
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "owner"
    assert body["tenant_id"] is not None
    assert body["branch_id"] is not None, "default branch should be assigned"
    assert "hashed_password" not in body


async def test_duplicate_slug_is_rejected(client: AsyncClient):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    again = await client.post("/api/v1/auth/signup", json={**SIGNUP, "email": "other@x.example"})
    assert again.status_code == 409
    assert again.json()["code"] == "slug_taken"


async def test_login_returns_tokens_and_me_returns_permissions(client: AsyncClient):
    tokens = await signup_and_login(client)
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["email"] == SIGNUP["email"]
    # The owner permission set drives what the frontend renders.
    assert "billing.manage" in body["permissions"]
    assert "platform.tenant.manage" not in body["permissions"]


async def test_wrong_password_is_indistinguishable_from_unknown_user(
    client: AsyncClient,
):
    await signup_and_login(client)
    wrong_password = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": "nope-nope-nope", "tenant_slug": "corner"},
    )
    unknown_user = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "ghost@corner.example",
            "password": "nope-nope-nope",
            "tenant_slug": "corner",
        },
    )
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["message"] == unknown_user.json()["message"]
    assert wrong_password.json()["code"] == "invalid_credentials"


async def test_account_locks_after_repeated_failures(client: AsyncClient):
    await signup_and_login(client)
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"email": SIGNUP["email"], "password": "wrong-one", "tenant_slug": "corner"},
        )
    # Correct password, but the account is now locked out.
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"], "tenant_slug": "corner"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "account_locked"


async def test_no_token_is_401_and_uses_the_standard_error_envelope(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    body = resp.json()
    assert set(body) == {"code", "message", "details", "request_id"}
    assert body["request_id"], "every error must carry a correlation id"


async def test_refresh_rotates_and_reuse_revokes_the_family(client: AsyncClient):
    tokens = await signup_and_login(client)
    first_refresh = tokens["refresh_token"]

    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first_refresh, "refresh tokens must be single-use"

    # Replaying the consumed token is treated as theft.
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert replay.status_code == 401
    assert "reuse" in replay.json()["message"].lower()

    # ...and the legitimate holder's token is revoked too, because we cannot
    # tell which party is the attacker.
    after = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}
    )
    assert after.status_code == 401


async def test_logout_revokes_the_refresh_token(client: AsyncClient):
    tokens = await signup_and_login(client)
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert out.status_code == 200
    reuse = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse.status_code == 401


async def test_token_from_one_shop_is_rejected_on_another_shops_subdomain(
    client: AsyncClient,
):
    """The subdomain never grants access, but a mismatch means replay."""
    tokens = await signup_and_login(client)
    await client.post(
        "/api/v1/auth/signup",
        json={**SIGNUP, "slug": "other", "email": "sam@other.example", "shop_name": "Other"},
    )
    resp = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {tokens['access_token']}",
            "Host": "other.localhost",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "permission_denied"


async def test_staff_listing_is_scoped_to_the_callers_shop(client: AsyncClient):
    """The core multi-tenancy guarantee, exercised through the HTTP API."""
    corner = await signup_and_login(client)
    await client.post(
        "/api/v1/auth/signup",
        json={**SIGNUP, "slug": "other", "email": "sam@other.example", "shop_name": "Other"},
    )

    resp = await client.get(
        "/api/v1/auth/terminal/staff",
        headers={"Authorization": f"Bearer {corner['access_token']}"},
    )
    assert resp.status_code == 200
    names = [u["full_name"] for u in resp.json()]
    assert names == ["Dana Owner"], f"leaked staff from another shop: {names}"
    assert "email" not in resp.json()[0]


async def test_tenant_user_cannot_log_in_without_a_shop_context(client: AsyncClient):
    """No subdomain and no slug means the platform namespace, where a shop
    user does not exist."""
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"]},
    )
    assert resp.status_code == 401


async def test_login_resolves_the_shop_from_the_subdomain(client: AsyncClient):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"]},
        headers={"Host": "corner.localhost"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


async def test_validation_errors_do_not_echo_the_submitted_value(client: AsyncClient):
    """A 422 must not hand the caller's own input back.

    FastAPI's raw `exc.errors()` includes an `input` key holding the offending
    value -- on signup that is the plaintext password, which would then travel
    into browser consoles and log aggregators. It also carries the original
    exception object for custom validators, which is not JSON-serialisable and
    turned every such 422 into a 500.
    """
    # A distinctive value, so a match in the response is unambiguous rather
    # than a collision with a pydantic error type like "string_too_short".
    canary = "Zx9QvLeak"  # 9 chars, one under the minimum
    resp = await client.post(
        "/api/v1/auth/signup",
        json={**SIGNUP, "password": canary},
    )
    assert resp.status_code == 422, resp.text

    body = resp.json()
    assert body["code"] == "validation_error"
    assert canary not in resp.text, "the submitted password was echoed back"

    errors = body["details"]["errors"]
    assert errors and set(errors[0]) == {"field", "message", "type"}
    assert errors[0]["field"] == "password"


async def test_custom_validator_failures_return_422_not_500(client: AsyncClient):
    """Slug rules are enforced by a field_validator raising ValueError."""
    reserved = await client.post("/api/v1/auth/signup", json={**SIGNUP, "slug": "admin"})
    assert reserved.status_code == 422
    assert reserved.json()["details"]["errors"][0]["field"] == "slug"

    malformed = await client.post("/api/v1/auth/signup", json={**SIGNUP, "slug": "Not A Slug!"})
    assert malformed.status_code == 422
