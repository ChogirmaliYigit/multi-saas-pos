import type { UserRole } from "@/lib/api/types";

/**
 * Mirrors app/core/permissions.py. These strings are used only to decide what
 * to *render* -- the API enforces the real thing. Hiding a button the server
 * would reject is a UX nicety, never a security control.
 */
export const Permission = {
  TENANT_READ: "tenant.read",
  TENANT_UPDATE: "tenant.update",

  USER_READ: "user.read",
  USER_CREATE: "user.create",
  USER_UPDATE: "user.update",
  USER_DELETE: "user.delete",

  BRANCH_READ: "branch.read",
  BRANCH_MANAGE: "branch.manage",

  CATEGORY_READ: "category.read",
  CATEGORY_MANAGE: "category.manage",
  PRODUCT_READ: "product.read",
  PRODUCT_MANAGE: "product.manage",
  PRODUCT_COST_READ: "product.cost.read",

  STOCK_READ: "stock.read",
  STOCK_ADJUST: "stock.adjust",

  ORDER_CREATE: "order.create",
  ORDER_READ: "order.read",
  ORDER_READ_ALL: "order.read_all",
  ORDER_DISCOUNT: "order.discount",
  ORDER_REFUND: "order.refund",
  ORDER_VOID: "order.void",

  SHIFT_OPEN: "shift.open",
  SHIFT_CLOSE: "shift.close",
  SHIFT_READ_ALL: "shift.read_all",

  CUSTOMER_READ: "customer.read",
  CUSTOMER_MANAGE: "customer.manage",

  REPORT_READ: "report.read",
  REPORT_EXPORT: "report.export",

  BILLING_READ: "billing.read",
  BILLING_MANAGE: "billing.manage",

  PLATFORM_TENANT_MANAGE: "platform.tenant.manage",
  PLATFORM_PLAN_MANAGE: "platform.plan.manage",
  PLATFORM_METRICS_READ: "platform.metrics.read",
} as const;

export type PermissionValue = (typeof Permission)[keyof typeof Permission];

/** Where each role lands after signing in. */
export const ROLE_HOME: Record<UserRole, string> = {
  super_admin: "/platform",
  owner: "/dashboard",
  manager: "/dashboard",
  cashier: "/pos",
};

export const ROLE_LABEL: Record<UserRole, string> = {
  super_admin: "Platform admin",
  owner: "Owner",
  manager: "Manager",
  cashier: "Cashier",
};
