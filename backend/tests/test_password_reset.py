"""Password reset.

The two properties that matter: it must not reveal who has an account, and a
link must work exactly once.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import engine

SIGNUP = {
    "shop_name": "Corner Store",
    "slug": "corner",
    "owner_name": "Dana Owner",
    "email": "dana@corner.example",
    "password": "correct-horse-battery",
    "plan_code": "basic",
}
NEW_PASSWORD = "a-completely-different-passphrase"


async def make_shop(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/signup", json=SIGNUP)
    assert resp.status_code == 201, resp.text


def token_from_log(caplog) -> str:
    """SMTP is unconfigured in tests, so email_service logs the message. That
    log is where the link lives."""
    match = re.search(r"reset-password\?token=([A-Za-z0-9_-]+)", caplog.text)
    assert match, f"no reset link in the logged email:\n{caplog.text[:600]}"
    return match.group(1)


async def request_reset(client: AsyncClient, caplog, email: str = SIGNUP["email"]) -> str:
    caplog.clear()
    with caplog.at_level("WARNING"):
        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": email, "tenant_slug": "corner"},
        )
    assert resp.status_code == 200
    return token_from_log(caplog)


# ---------------------------------------------------------------------------
# Not revealing who has an account
# ---------------------------------------------------------------------------


async def test_unknown_address_gets_the_same_answer(client: AsyncClient):
    """Otherwise this form is a directory of who works at a shop."""
    await make_shop(client)

    known = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": SIGNUP["email"], "tenant_slug": "corner"},
    )
    unknown = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nobody@corner.example", "tenant_slug": "corner"},
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


async def test_unknown_shop_gets_the_same_answer(client: AsyncClient):
    await make_shop(client)
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": SIGNUP["email"], "tenant_slug": "no-such-shop"},
    )
    assert resp.status_code == 200


async def test_no_token_is_issued_for_an_unknown_address(client: AsyncClient):
    await make_shop(client)
    await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nobody@corner.example", "tenant_slug": "corner"},
    )
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        count = await conn.scalar(text("SELECT count(*) FROM password_reset_tokens"))
    assert count == 0, "a token was created for an address with no account"


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


async def test_reset_changes_the_password(client: AsyncClient, caplog):
    await make_shop(client)
    token = await request_reset(client, caplog)

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 200, resp.text

    old = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"], "tenant_slug": "corner"},
    )
    assert old.status_code == 401, "the old password still works"

    new = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": NEW_PASSWORD, "tenant_slug": "corner"},
    )
    assert new.status_code == 200


async def test_reset_signs_out_every_other_session(client: AsyncClient, caplog):
    """People reset a password because they think a session is not theirs."""
    await make_shop(client)
    signed_in = (
        await client.post(
            "/api/v1/auth/login",
            json={
                "email": SIGNUP["email"],
                "password": SIGNUP["password"],
                "tenant_slug": "corner",
            },
        )
    ).json()

    token = await request_reset(client, caplog)
    await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": signed_in["refresh_token"]}
    )
    assert refreshed.status_code == 401, "an existing session survived the reset"


async def test_reset_clears_a_lockout(client: AsyncClient, caplog):
    """A lockout must not outlive the reset that fixes it."""
    await make_shop(client)
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"email": SIGNUP["email"], "password": "wrong-one", "tenant_slug": "corner"},
        )
    locked = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": SIGNUP["password"], "tenant_slug": "corner"},
    )
    assert locked.json()["code"] == "account_locked"

    token = await request_reset(client, caplog)
    await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": SIGNUP["email"], "password": NEW_PASSWORD, "tenant_slug": "corner"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Token rules
# ---------------------------------------------------------------------------


async def test_a_link_works_only_once(client: AsyncClient, caplog):
    await make_shop(client)
    token = await request_reset(client, caplog)

    first = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "yet-another-passphrase"},
    )
    assert second.status_code == 401
    assert second.json()["code"] == "invalid_reset_token"


async def test_requesting_again_invalidates_the_previous_link(client: AsyncClient, caplog):
    """Two live links in two inboxes is one more than anybody needs."""
    await make_shop(client)
    first_token = await request_reset(client, caplog)
    second_token = await request_reset(client, caplog)
    assert first_token != second_token

    stale = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": first_token, "new_password": NEW_PASSWORD},
    )
    assert stale.status_code == 401

    fresh = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": second_token, "new_password": NEW_PASSWORD},
    )
    assert fresh.status_code == 200


async def test_an_expired_link_is_refused(client: AsyncClient, caplog):
    await make_shop(client)
    token = await request_reset(client, caplog)

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        await conn.execute(
            text("UPDATE password_reset_tokens SET expires_at = :past"),
            {"past": datetime.now(UTC) - timedelta(minutes=1)},
        )

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_reset_token"


async def test_a_made_up_token_is_refused(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "x" * 43, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_reset_token"


async def test_tokens_are_stored_hashed(client: AsyncClient, caplog):
    """A database leak must not hand over a working reset link for every
    account that has requested one."""
    await make_shop(client)
    token = await request_reset(client, caplog)

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        stored = await conn.scalar(text("SELECT token_hash FROM password_reset_tokens"))

    assert stored != token
    assert len(stored) == 64, "expected a sha-256 digest"


async def test_a_weak_new_password_is_refused(client: AsyncClient, caplog):
    await make_shop(client)
    token = await request_reset(client, caplog)
    resp = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "short"}
    )
    assert resp.status_code == 422
    # And the token survives, so the user can try again with a better one.
    retry = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert retry.status_code == 200


async def test_a_suspended_shop_cannot_reset_its_way_back_in(client: AsyncClient, caplog):
    await make_shop(client)
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        await conn.execute(text("UPDATE tenants SET status = 'SUSPENDED' WHERE slug = 'corner'"))

    caplog.clear()
    with caplog.at_level("WARNING"):
        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": SIGNUP["email"], "tenant_slug": "corner"},
        )
    assert resp.status_code == 200
    assert "reset-password?token=" not in caplog.text

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.is_platform = 'on'"))
        count = await conn.scalar(text("SELECT count(*) FROM password_reset_tokens"))
    assert count == 0
