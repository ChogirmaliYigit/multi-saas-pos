import type { UserRole } from "./types";

export interface DashboardSummary {
  currency: string;
  revenue_today: string;
  revenue_yesterday: string;
  orders_today: number;
  average_basket: string;
  gross_margin_today: string;
  revenue_month: string;
  low_stock_count: number;
  out_of_stock_count: number;
  active_shifts: number;
}

export interface RevenuePoint {
  day: string;
  revenue: string;
  orders: number;
  margin: string;
}

export interface TopProduct {
  product_id: string | null;
  name: string;
  sku: string | null;
  quantity_sold: string;
  revenue: string;
  margin: string;
}

export interface LowStockItem {
  product_id: string;
  name: string;
  sku: string;
  branch_id: string;
  branch_name: string;
  quantity: string;
  threshold: string;
}

export interface PaymentBreakdown {
  method: string;
  total: string;
  count: number;
}

export interface SalesByHour {
  hour: number;
  revenue: string;
  orders: number;
}

export interface PlanUsage {
  plan_name: string | null;
  products: { used: number; limit: number | null };
  users: { used: number; limit: number | null };
  branches: { used: number; limit: number | null };
  orders_this_month: { used: number; limit: number | null };
}

/** A row from the catalog list. Cost is null unless the caller may see it. */
export interface ProductListItem {
  id: string;
  name: string;
  sku: string;
  barcode: string | null;
  category_id: string | null;
  category_name: string | null;
  unit: string;
  price: string;
  image_url: string | null;
  track_stock: boolean;
  is_favorite: boolean;
  is_active: boolean;
  tax_rate: string;
  tax_inclusive: boolean;
  stock_quantity: string | null;
  low_stock: boolean;
  low_stock_threshold: string | null;
  cost_price: string | null;
}

export interface ProductDetail {
  id: string;
  name: string;
  description: string | null;
  sku: string;
  barcode: string | null;
  category_id: string | null;
  category_name: string | null;
  tax_rate_id: string | null;
  tax_rate_name: string | null;
  unit: string;
  price: string;
  cost_price: string;
  image_url: string | null;
  track_stock: boolean;
  low_stock_threshold: string;
  is_active: boolean;
  is_favorite: boolean;
  tax_rate: string;
  tax_inclusive: boolean;
  stock_quantity: string | null;
  low_stock: boolean;
}

export interface TaxRate {
  id: string;
  name: string;
  rate: string;
  is_inclusive: boolean;
  is_default: boolean;
  is_active: boolean;
}

export interface StockLevel {
  product_id: string;
  product_name: string;
  sku: string;
  barcode: string | null;
  branch_id: string;
  branch_name: string;
  quantity: string;
  reserved_quantity: string;
  available: string;
  low_stock_threshold: string;
  is_low: boolean;
  unit: string;
  cost_price: string;
  stock_value: string;
}

export interface StockMovement {
  id: string;
  product_id: string;
  branch_id: string;
  movement_type: string;
  quantity: string;
  quantity_after: string;
  unit_cost: string | null;
  reference_type: string | null;
  reference_id: string | null;
  note: string | null;
  created_at: string;
  created_by_id: string | null;
}

export interface Employee {
  id: string;
  full_name: string;
  email: string;
  role: UserRole;
  branch_id: string | null;
  phone: string | null;
  avatar_url: string | null;
  is_active: boolean;
  has_pin: boolean;
  last_login_at: string | null;
  created_at: string;
  permissions: string[];
}

export type ReportType =
  "sales_summary" | "sales_detailed" | "tax" | "inventory" | "employee_performance";

export type ReportStatus = "pending" | "running" | "completed" | "failed";

export interface ReportJob {
  id: string;
  report_type: ReportType;
  export_format: "csv" | "pdf" | "xlsx";
  status: ReportStatus;
  params: Record<string, string>;
  branch_id: string | null;
  file_size_bytes: number | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  expires_at: string | null;
  is_downloadable: boolean;
}
