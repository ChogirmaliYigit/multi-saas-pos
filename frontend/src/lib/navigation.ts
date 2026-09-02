import {
  BarChart3,
  Boxes,
  Building2,
  CreditCard,
  LayoutDashboard,
  type LucideIcon,
  Package,
  Receipt,
  Settings,
  ShoppingCart,
  Tags,
  Users,
} from "lucide-react";

import { Permission, type PermissionValue } from "@/lib/permissions";

export interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
  /** Hidden unless the session carries this permission. */
  permission?: PermissionValue;
  exact?: boolean;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

/** Tenant admin panel (owner / manager). */
export const shopNavigation: NavSection[] = [
  {
    label: "Overview",
    items: [
      {
        title: "Dashboard",
        href: "/dashboard",
        icon: LayoutDashboard,
        exact: true,
      },
      {
        title: "Sales",
        href: "/sales",
        icon: Receipt,
        permission: Permission.ORDER_READ_ALL,
      },
      {
        title: "Reports",
        href: "/reports",
        icon: BarChart3,
        permission: Permission.REPORT_READ,
      },
    ],
  },
  {
    label: "Catalog",
    items: [
      {
        title: "Products",
        href: "/products",
        icon: Package,
        permission: Permission.PRODUCT_READ,
      },
      {
        title: "Categories",
        href: "/categories",
        icon: Tags,
        permission: Permission.CATEGORY_READ,
      },
      {
        title: "Inventory",
        href: "/inventory",
        icon: Boxes,
        permission: Permission.STOCK_READ,
      },
    ],
  },
  {
    label: "Shop",
    items: [
      {
        title: "Employees",
        href: "/employees",
        icon: Users,
        permission: Permission.USER_READ,
      },
      {
        title: "Branches",
        href: "/branches",
        icon: Building2,
        permission: Permission.BRANCH_READ,
      },
      {
        title: "Billing",
        href: "/billing",
        icon: CreditCard,
        permission: Permission.BILLING_READ,
      },
      {
        title: "Settings",
        href: "/settings",
        icon: Settings,
        permission: Permission.TENANT_READ,
      },
    ],
  },
];

/** Super admin panel (SaaS operator). */
export const platformNavigation: NavSection[] = [
  {
    label: "Platform",
    items: [
      { title: "Overview", href: "/platform", icon: LayoutDashboard, exact: true },
      { title: "Tenants", href: "/platform/tenants", icon: Building2 },
      { title: "Plans", href: "/platform/plans", icon: CreditCard },
    ],
  },
];

export const posEntry: NavItem = {
  title: "Open POS terminal",
  href: "/pos",
  icon: ShoppingCart,
  permission: Permission.ORDER_CREATE,
};
