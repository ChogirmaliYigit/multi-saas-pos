from __future__ import annotations

from app.models.enums import UserRole


class Permission:
    """Action strings checked by the `require` dependency.

    Deliberately flat and explicit. A permission table in the database would be
    more flexible, but flexibility here means an owner can lock themselves out
    of their own shop; the fixed matrix below is auditable at a glance.
    """

    TENANT_READ = "tenant.read"
    TENANT_UPDATE = "tenant.update"

    USER_READ = "user.read"
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"

    BRANCH_READ = "branch.read"
    BRANCH_MANAGE = "branch.manage"

    CATEGORY_READ = "category.read"
    CATEGORY_MANAGE = "category.manage"
    PRODUCT_READ = "product.read"
    PRODUCT_MANAGE = "product.manage"
    PRODUCT_COST_READ = "product.cost.read"  # margins are owner-level data

    STOCK_READ = "stock.read"
    STOCK_ADJUST = "stock.adjust"

    ORDER_CREATE = "order.create"
    ORDER_READ = "order.read"
    ORDER_READ_ALL = "order.read_all"  # beyond one's own shift
    ORDER_DISCOUNT = "order.discount"
    ORDER_REFUND = "order.refund"
    ORDER_VOID = "order.void"

    SHIFT_OPEN = "shift.open"
    SHIFT_CLOSE = "shift.close"
    SHIFT_READ_ALL = "shift.read_all"

    CUSTOMER_READ = "customer.read"
    CUSTOMER_MANAGE = "customer.manage"

    REPORT_READ = "report.read"
    REPORT_EXPORT = "report.export"

    BILLING_READ = "billing.read"
    BILLING_MANAGE = "billing.manage"

    # Platform-only, never granted to a tenant role.
    PLATFORM_TENANT_MANAGE = "platform.tenant.manage"
    PLATFORM_PLAN_MANAGE = "platform.plan.manage"
    PLATFORM_METRICS_READ = "platform.metrics.read"


_CASHIER: frozenset[str] = frozenset(
    {
        Permission.PRODUCT_READ,
        Permission.CATEGORY_READ,
        Permission.STOCK_READ,
        Permission.ORDER_CREATE,
        Permission.ORDER_READ,
        Permission.SHIFT_OPEN,
        Permission.SHIFT_CLOSE,
        Permission.CUSTOMER_READ,
        Permission.CUSTOMER_MANAGE,
        Permission.BRANCH_READ,
    }
)

# A manager runs the floor: full inventory and reporting, plus refunds and
# voids. Cannot touch billing, cannot delete staff, cannot change shop settings.
_MANAGER: frozenset[str] = _CASHIER | frozenset(
    {
        Permission.TENANT_READ,
        Permission.USER_READ,
        Permission.USER_CREATE,
        Permission.USER_UPDATE,
        Permission.CATEGORY_MANAGE,
        Permission.PRODUCT_MANAGE,
        Permission.PRODUCT_COST_READ,
        Permission.STOCK_ADJUST,
        Permission.ORDER_READ_ALL,
        Permission.ORDER_DISCOUNT,
        Permission.ORDER_REFUND,
        Permission.ORDER_VOID,
        Permission.SHIFT_READ_ALL,
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
    }
)

_OWNER: frozenset[str] = _MANAGER | frozenset(
    {
        Permission.TENANT_UPDATE,
        Permission.USER_DELETE,
        Permission.BRANCH_MANAGE,
        Permission.BILLING_READ,
        Permission.BILLING_MANAGE,
    }
)

_SUPER_ADMIN: frozenset[str] = frozenset(
    {
        Permission.PLATFORM_TENANT_MANAGE,
        Permission.PLATFORM_PLAN_MANAGE,
        Permission.PLATFORM_METRICS_READ,
    }
)

ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.CASHIER: _CASHIER,
    UserRole.MANAGER: _MANAGER,
    UserRole.OWNER: _OWNER,
    UserRole.SUPER_ADMIN: _SUPER_ADMIN,
}


def permissions_for(role: UserRole, overrides: dict | None = None) -> frozenset[str]:
    """Role defaults, then per-user overrides.

    Deny is applied after allow, so revoking a permission always wins -- an
    owner taking refund rights away from one manager cannot be undone by an
    allow entry added later.
    """
    granted = set(ROLE_PERMISSIONS.get(role, frozenset()))
    if overrides:
        granted |= set(overrides.get("allow", []))
        granted -= set(overrides.get("deny", []))
    return frozenset(granted)


def has_permission(role: UserRole, permission: str, overrides: dict | None = None) -> bool:
    return permission in permissions_for(role, overrides)
