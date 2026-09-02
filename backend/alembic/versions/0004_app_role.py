"""create the unprivileged application role

Revision ID: 0004_app_role
Revises: 0003_row_level_security
Create Date: 2026-09-01

The API and Celery workers connect as this role. It is deliberately NOT the
schema owner and NOT a superuser, because PostgreSQL exempts both from row
level security -- connecting as the owner would quietly disable every policy
created in 0003 while leaving them visible in pg_policies.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op
from app.core.config import settings

revision: str = "0004_app_role"
down_revision: str | None = "0003_row_level_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Through Settings, not os.getenv: pydantic-settings loads .env into the
# settings object and NOT into the process environment, so os.getenv would
# silently fall back to the default password for anyone running migrations
# from a .env file rather than exported shell variables.
APP_ROLE = settings.POSTGRES_USER
APP_PASSWORD = settings.POSTGRES_PASSWORD


def upgrade() -> None:
    conn = op.get_bind()
    database = conn.engine.url.database

    # CREATE ROLE accepts no bind parameters, so the name and password are
    # passed through GUCs and quoted by format()'s %I/%L -- never by string
    # concatenation, which would make the DB password a SQL-injection vector
    # against the migration itself.
    conn.execute(text("SELECT set_config('pos.app_role', :role, false)"), {"role": APP_ROLE})
    conn.execute(text("SELECT set_config('pos.app_password', :pwd, false)"), {"pwd": APP_PASSWORD})
    op.execute(
        """
        DO $$
        DECLARE
            v_role text := current_setting('pos.app_role');
            v_pwd  text := current_setting('pos.app_password');
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
                EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L', v_role, v_pwd);
            ELSE
                EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', v_role, v_pwd);
            END IF;
            -- Must never bypass RLS, whatever it was granted previously.
            EXECUTE format('ALTER ROLE %I NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE', v_role);
        END
        $$;
        """
    )

    # DML only. No DDL, no ownership -- a compromised API cannot drop a policy.
    op.execute(f'GRANT CONNECT ON DATABASE "{database}" TO "{APP_ROLE}"')
    op.execute(f'GRANT USAGE ON SCHEMA public TO "{APP_ROLE}"')
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{APP_ROLE}"'
    )
    op.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{APP_ROLE}"')
    # Tables created by future migrations inherit the same grants.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{APP_ROLE}"'
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f'GRANT USAGE, SELECT ON SEQUENCES TO "{APP_ROLE}"'
    )


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM "{APP_ROLE}"'
    )
    op.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{APP_ROLE}"')
    op.execute(f'REVOKE ALL ON SCHEMA public FROM "{APP_ROLE}"')
    op.execute(f'DROP ROLE IF EXISTS "{APP_ROLE}"')
