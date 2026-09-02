import { api } from "./client";
import type {
  Category,
  Order,
  Product,
  ProductLookup,
  Receipt,
  Shift,
  ShiftSummary,
} from "./pos-types";
import type {
  DashboardSummary,
  Employee,
  LowStockItem,
  PaymentBreakdown,
  PlanUsage,
  ProductDetail,
  ProductListItem,
  ReportJob,
  RevenuePoint,
  SalesByHour,
  StockLevel,
  StockMovement,
  TaxRate,
  TopProduct,
} from "./admin-types";
import type {
  MrrPoint,
  Plan,
  PlatformMetrics,
  TenantSummary,
} from "./platform-types";
import type { Page, SessionInfo, TerminalStaff, UserPublic } from "./types";

/**
 * One module per resource keeps React Query hooks free of URL strings, so a
 * route rename is a single-line change.
 */
export const authApi = {
  session: () => api.get<SessionInfo>("/auth/me"),
  terminalStaff: () => api.get<TerminalStaff[]>("/auth/terminal/staff"),
  pinLogin: (userId: string, pin: string) =>
    api.post<{ access_token: string; expires_in: number }>("/auth/pin-login", {
      user_id: userId,
      pin,
    }),
  changePassword: (currentPassword: string, newPassword: string) =>
    api.post<{ message: string }>("/auth/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  setPin: (pin: string) => api.post<{ message: string }>("/auth/set-pin", { pin }),
};

/** Auth flows that must go through the BFF so the refresh cookie is set. */
export const sessionApi = {
  login: async (input: {
    email: string;
    password: string;
    tenant_slug?: string | null;
  }) =>
    postToBff<{ access_token: string; expires_in: number }>(
      "/api/auth/login",
      input,
    ),

  signup: async (input: Record<string, unknown>) =>
    postToBff<{ user: UserPublic; access_token?: string; expires_in?: number }>(
      "/api/auth/signup",
      input,
    ),

  logout: async () => postToBff<{ message: string }>("/api/auth/logout"),
};

async function postToBff<T>(path: string, body?: unknown): Promise<T> {
  const { ApiError } = await import("./errors");
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, payload);
  }
  return payload as T;
}

export const catalogApi = {
  categories: () => api.get<Category[]>("/catalog/categories"),

  products: (params: {
    search?: string;
    category_id?: string;
    favorites_only?: boolean;
    page?: number;
    size?: number;
  }) => api.get<Page<Product>>("/catalog/products", { query: params }),

  /** Barcode or SKU. The hot path -- one indexed lookup per scan. */
  lookup: (code: string) =>
    api.get<ProductLookup>("/catalog/lookup", { query: { code } }),
};

export const ordersApi = {
  create: (body: {
    items: {
      product_id: string;
      quantity: string;
      discount_type?: string;
      discount_value?: string;
    }[];
    payments: {
      method: string;
      amount: string;
      tendered_amount?: string;
      reference?: string;
      card_last4?: string;
    }[];
    discount_type?: string;
    discount_value?: string;
    customer_id?: string | null;
    note?: string | null;
    idempotency_key: string;
  }) => api.post<Order>("/orders", body),

  get: (id: string) => api.get<Order>(`/orders/${id}`),
  receipt: (id: string) => api.get<Receipt>(`/orders/${id}/receipt`),
  list: (params: { page?: number; size?: number } = {}) =>
    api.get<Page<Order>>("/orders", { query: params }),
};

export const shiftsApi = {
  current: () => api.get<Shift | null>("/shifts/current"),
  open: (openingFloat: string) =>
    api.post<Shift>("/shifts/open", { opening_float: openingFloat }),
  summary: () => api.get<ShiftSummary>("/shifts/current/summary"),
  close: (countedCash: string, note?: string) =>
    api.post<Shift>("/shifts/current/close", {
      counted_cash: countedCash,
      note: note ?? null,
    }),
};

export const analyticsApi = {
  dashboard: (branchId?: string) =>
    api.get<DashboardSummary>("/analytics/dashboard", {
      query: { branch_id: branchId },
    }),
  revenue: (days = 30) =>
    api.get<RevenuePoint[]>("/analytics/revenue", { query: { days } }),
  topProducts: (days = 30, limit = 8) =>
    api.get<TopProduct[]>("/analytics/top-products", { query: { days, limit } }),
  lowStock: (limit = 20) =>
    api.get<LowStockItem[]>("/analytics/low-stock", { query: { limit } }),
  payments: (days = 30) =>
    api.get<PaymentBreakdown[]>("/analytics/payments", { query: { days } }),
  hourly: (days = 7) =>
    api.get<SalesByHour[]>("/analytics/hourly", { query: { days } }),
  usage: () => api.get<PlanUsage>("/analytics/usage"),
};

export const productsApi = {
  list: (params: {
    search?: string;
    category_id?: string;
    page?: number;
    size?: number;
  }) => api.get<Page<ProductListItem>>("/catalog/products", { query: params }),
  get: (id: string) => api.get<ProductDetail>(`/catalog/products/${id}`),
  create: (body: Record<string, unknown>) =>
    api.post<ProductDetail>("/catalog/products", body),
  update: (id: string, body: Record<string, unknown>) =>
    api.patch<ProductDetail>(`/catalog/products/${id}`, body),
  remove: (id: string) =>
    api.delete<{ message: string }>(`/catalog/products/${id}`),
  taxRates: () => api.get<TaxRate[]>("/catalog/tax-rates"),
};

export const categoriesApi = {
  list: () => catalogApi.categories(),
  create: (body: { name: string; color?: string | null }) =>
    api.post("/catalog/categories", body),
  update: (id: string, body: Record<string, unknown>) =>
    api.patch(`/catalog/categories/${id}`, body),
  remove: (id: string) =>
    api.delete<{ message: string }>(`/catalog/categories/${id}`),
};

export const inventoryApi = {
  levels: (params: {
    search?: string;
    low_only?: boolean;
    page?: number;
    size?: number;
  }) => api.get<Page<StockLevel>>("/inventory/levels", { query: params }),
  adjust: (body: {
    product_id: string;
    quantity: string;
    movement_type?: string;
    note?: string | null;
  }) => api.post<StockMovement>("/inventory/adjust", body),
  count: (body: {
    product_id: string;
    counted_quantity: string;
    note?: string | null;
  }) => api.post<StockMovement>("/inventory/count", body),
  movements: (params: { product_id?: string; page?: number; size?: number }) =>
    api.get<Page<StockMovement>>("/inventory/movements", { query: params }),
};

export const employeesApi = {
  list: (
    params: { search?: string; include_inactive?: boolean; page?: number } = {},
  ) => api.get<Page<Employee>>("/employees", { query: params }),
  create: (body: Record<string, unknown>) => api.post<Employee>("/employees", body),
  update: (id: string, body: Record<string, unknown>) =>
    api.patch<Employee>(`/employees/${id}`, body),
  resetPassword: (id: string, newPassword: string) =>
    api.post<{ message: string }>(`/employees/${id}/reset-password`, {
      new_password: newPassword,
    }),
  remove: (id: string) => api.delete<{ message: string }>(`/employees/${id}`),
};

export const reportsApi = {
  list: () => api.get<Page<ReportJob>>("/reports", { query: { size: 25 } }),
  get: (id: string) => api.get<ReportJob>(`/reports/${id}`),
  request: (body: {
    report_type: string;
    export_format: string;
    date_from: string;
    date_to: string;
  }) => api.post<ReportJob>("/reports", body),
  downloadUrl: (id: string) => `/reports/${id}/download`,
};

export const platformApi = {
  metrics: () => api.get<PlatformMetrics>("/platform/metrics"),
  mrr: (months = 12) => api.get<MrrPoint[]>("/platform/mrr", { query: { months } }),

  tenants: (params: {
    search?: string;
    tenant_status?: string;
    page?: number;
    size?: number;
  }) => api.get<Page<TenantSummary>>("/platform/tenants", { query: params }),

  createTenant: (body: Record<string, unknown>) =>
    api.post<TenantSummary>("/platform/tenants", body),

  setTenantStatus: (id: string, status: string, reason?: string | null) =>
    api.patch<TenantSummary>(`/platform/tenants/${id}/status`, {
      status,
      reason: reason ?? null,
    }),

  changeTenantPlan: (
    id: string,
    body: { plan_id: string; billing_cycle?: string; activate?: boolean },
  ) => api.patch<TenantSummary>(`/platform/tenants/${id}/plan`, body),

  closeTenant: (id: string) =>
    api.delete<{ message: string }>(`/platform/tenants/${id}`),

  plans: () => api.get<Plan[]>("/platform/plans"),
  createPlan: (body: Record<string, unknown>) =>
    api.post<Plan>("/platform/plans", body),
  updatePlan: (id: string, body: Record<string, unknown>) =>
    api.patch<Plan>(`/platform/plans/${id}`, body),
  retirePlan: (id: string) =>
    api.delete<{ message: string }>(`/platform/plans/${id}`),
};
