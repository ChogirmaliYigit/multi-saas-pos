from __future__ import annotations

from app.db.mixins import OptionalTenantMixin, TenantMixin
from app.models import Base

# Policy text is generated from the models rather than hand-written per table.
# A new tenant-owned model therefore cannot ship without RLS -- the test in
# tests/test_rls.py fails the build if a table is missing a policy.
POLICY_NAME = "tenant_isolation"

_TENANT_MATCH = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_PLATFORM = "current_setting('app.is_platform', true) = 'on'"
# Authentication has to read `users` and write `refresh_tokens` *before* any
# tenant is known -- that is what logging in means. Rather than leave those
# tables unprotected, they get one narrow, explicitly named escape hatch that
# only app.services.auth_service turns on, and only around the credential
# lookup itself.
_AUTH_LOOKUP = "current_setting('app.auth_lookup', true) = 'on'"

_PREDICATE = f"{_TENANT_MATCH} OR {_PLATFORM}"
_OPTIONAL_PREDICATE = f"{_TENANT_MATCH} OR {_PLATFORM} OR {_AUTH_LOOKUP}"


def tenant_owned_tables() -> list[str]:
    """Tables with a NOT NULL tenant_id."""
    return sorted(
        mapper.class_.__tablename__
        for mapper in Base.registry.mappers
        if issubclass(mapper.class_, TenantMixin)
    )


def optional_tenant_tables() -> list[str]:
    """Tables with a nullable tenant_id: users, refresh_tokens, audit_logs."""
    return sorted(
        mapper.class_.__tablename__
        for mapper in Base.registry.mappers
        if issubclass(mapper.class_, OptionalTenantMixin)
    )


def all_protected_tables() -> list[str]:
    return sorted(set(tenant_owned_tables()) | set(optional_tenant_tables()))


def enable_rls_sql(table: str, *, allow_auth_lookup: bool = False) -> list[str]:
    predicate = _OPTIONAL_PREDICATE if allow_auth_lookup else _PREDICATE
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        # FORCE also applies the policy to the table's owner. Without it, the
        # role that ran the migrations would silently bypass every policy.
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}",
        f"CREATE POLICY {POLICY_NAME} ON {table} " f"USING ({predicate}) WITH CHECK ({predicate})",
    ]


def disable_rls_sql(table: str) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]
