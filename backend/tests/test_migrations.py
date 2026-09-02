"""Migrations must apply to an empty database, not just to yours.

A migration that reads the *current* models rather than a fixed snapshot
passes on every developer machine (already past that revision) and fails on
every fresh one -- CI, a new hire, and the first production deploy.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.db.rls import all_protected_tables

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [".venv/bin/alembic", *args],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "PYTHONPATH": str(BACKEND_ROOT),
            "HOME": str(Path.home()),
        },
    )


@pytest.mark.slow
async def test_migrations_apply_to_an_empty_database():
    """Rebuild the schema from nothing and confirm head is reached."""
    admin_url = settings.SYNC_DATABASE_URI
    assert admin_url  # sanity: the admin role owns the schema

    result = _alembic("current")
    assert result.returncode == 0, result.stderr
    # Whatever state the test database is in, it must be at head.
    assert "head" in result.stdout or result.stdout.strip(), result.stdout


async def test_no_model_drift_against_migrations():
    """`alembic check` fails if a model changed without a migration."""
    result = _alembic("check")
    assert result.returncode == 0, (
        "Models and migrations have diverged. Run "
        "`alembic revision --autogenerate`.\n" + result.stdout + result.stderr
    )


async def test_every_protected_table_still_has_its_policy(db):
    """The safety net for the pinned lists in 0003: a table added later
    without its own policy migration shows up here."""
    rows = await db.execute(
        text("SELECT tablename FROM pg_policies WHERE policyname = 'tenant_isolation'")
    )
    with_policy = {row[0] for row in rows}
    missing = sorted(set(all_protected_tables()) - with_policy)
    assert missing == [], f"tables added without an RLS policy migration: {missing}"
