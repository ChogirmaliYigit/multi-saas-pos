from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.core.context import get_current_tenant_id, get_principal
from app.db.mixins import OptionalTenantMixin, TenantMixin

# Escape hatch for the handful of legitimate cross-tenant reads (super-admin
# dashboards, the login lookup that has no tenant yet, Celery rollups):
#     session.execute(stmt.execution_options(skip_tenant_filter=True))
SKIP_TENANT_FILTER = "skip_tenant_filter"


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(execute_state) -> None:  # type: ignore[no-untyped-def]
    """Append `WHERE tenant_id = :current` to every ORM read.

    This is layer 2 of 3. It exists so that a handler which forgets to filter
    still cannot return another shop's rows -- the criteria is attached to the
    mixin, so it covers every current and future tenant-owned model, including
    eagerly-loaded relationships and aliases.
    """
    if not execute_state.is_select:
        return
    if execute_state.is_column_load or execute_state.is_relationship_load:
        # Refreshing an already-loaded object; the parent query was filtered.
        return
    if execute_state.execution_options.get(SKIP_TENANT_FILTER, False):
        return

    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        return

    # Both mixins, not just the strict one. On OptionalTenantMixin tables the
    # equality also excludes the NULL-tenant platform rows, which is correct:
    # a shop must not see platform staff in its own staff list.
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantMixin,
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
        ),
        with_loader_criteria(
            OptionalTenantMixin,
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
        ),
    )


@event.listens_for(Session, "before_flush")
def _stamp_tenant_on_insert(session: Session, flush_context, instances) -> None:  # type: ignore[no-untyped-def]
    """Stamp tenant_id on every new tenant-owned row.

    Handlers never set tenant_id themselves, so a client-supplied value in a
    request body has nothing to attach to. If a row for another tenant is
    somehow constructed in code, this raises rather than writing it.
    """
    tenant_id = get_current_tenant_id()
    principal = get_principal()

    for obj in session.new:
        if not isinstance(obj, TenantMixin | OptionalTenantMixin):
            continue
        current = getattr(obj, "tenant_id", None)
        if current is None:
            if isinstance(obj, OptionalTenantMixin) and tenant_id is None:
                continue  # platform-owned row, e.g. a super-admin account
            if tenant_id is None:
                raise RuntimeError(
                    f"Refusing to insert {type(obj).__name__} with no tenant in context. "
                    "Wrap the operation in tenant_scope(...) or set tenant_id explicitly."
                )
            obj.tenant_id = tenant_id
        elif tenant_id is not None and current != tenant_id:
            if not (principal and principal.is_platform_staff):
                raise RuntimeError(
                    f"Cross-tenant write blocked: {type(obj).__name__} "
                    f"targets {current}, request is scoped to {tenant_id}."
                )
