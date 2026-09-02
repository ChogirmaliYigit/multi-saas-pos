"""enable row level security on every tenant-owned table

Revision ID: 0003_row_level_security
Revises: 0002_initial_schema
Create Date: 2026-09-01

Layer 3 of tenant isolation.

The table lists below are written out literally rather than derived from the
models, and that is deliberate. An earlier version called
`tenant_owned_tables()`, which reflects whatever the models look like *today* --
so adding a new tenant-owned model made this historical migration try to
ALTER a table that does not exist until three revisions later. It broke every
fresh database while leaving already-migrated ones working, which is the worst
possible failure shape: invisible in development, fatal in CI and on first
deploy.

A migration is a snapshot of history. New tables carry their own policy in
their own revision, and `tests/test_rls.py` fails the build if any tenant-owned
table ever ends up without one.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.db.rls import disable_rls_sql, enable_rls_sql

revision: str = "0003_row_level_security"
down_revision: str | None = "0002_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables with a NOT NULL tenant_id, as of this revision.
TENANT_OWNED = [
    "branches",
    "categories",
    "customers",
    "order_items",
    "orders",
    "payments",
    "product_barcodes",
    "products",
    "refunds",
    "report_jobs",
    "shifts",
    "stock_items",
    "stock_movements",
    "suppliers",
    "tax_rates",
]

# Nullable tenant_id: platform staff and platform-level events belong to no
# shop. Same protection, plus the one named escape hatch authentication needs
# before a tenant is known.
OPTIONAL_TENANT = ["audit_logs", "refresh_tokens", "users"]


def upgrade() -> None:
    for table in TENANT_OWNED:
        for statement in enable_rls_sql(table):
            op.execute(statement)

    for table in OPTIONAL_TENANT:
        for statement in enable_rls_sql(table, allow_auth_lookup=True):
            op.execute(statement)


def downgrade() -> None:
    for table in TENANT_OWNED + OPTIONAL_TENANT:
        for statement in disable_rls_sql(table):
            op.execute(statement)
