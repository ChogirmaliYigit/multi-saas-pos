"""enable required postgres extensions

Revision ID: 0001_extensions
Revises:
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_extensions"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Trigram matching for the POS product search box ("coca" -> "Coca-Cola").
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # Lets a plain btree column (tenant_id) sit inside a GIN index alongside
    # the trigram column, so the search index stays tenant-scoped.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS btree_gin")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
