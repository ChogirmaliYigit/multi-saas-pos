export type TenantStatus = "trial" | "active" | "suspended" | "cancelled";
export type SubscriptionStatus =
  "trialing" | "active" | "past_due" | "canceled" | "expired";
export type BillingCycle = "monthly" | "yearly";

export interface PlatformMetrics {
  total_tenants: number;
  active_tenants: number;
  trialing_tenants: number;
  suspended_tenants: number;
  mrr: string;
  arr: string;
  trial_pipeline_mrr: string;
  currency: string;
  new_tenants_this_month: number;
  churned_this_month: number;
  total_users: number;
  orders_last_30_days: number;
  gmv_last_30_days: string;
}

export interface MrrPoint {
  month: string;
  mrr: string;
  tenants: number;
}

export interface TenantSummary {
  id: string;
  name: string;
  slug: string;
  email: string;
  status: TenantStatus;
  currency: string;
  country_code: string;
  created_at: string;
  trial_ends_at: string | null;
  blocked_reason: string | null;
  plan_name: string | null;
  plan_code: string | null;
  subscription_status: SubscriptionStatus | null;
  billing_cycle: BillingCycle | null;
  mrr: string;
  user_count: number;
  product_count: number;
  orders_last_30_days: number;
  gmv_last_30_days: string;
  last_activity_at: string | null;
}

export interface Plan {
  id: string;
  code: string;
  name: string;
  description: string | null;
  price_monthly: string;
  price_yearly: string;
  currency: string;
  trial_days: number;
  max_branches: number | null;
  max_users: number | null;
  max_products: number | null;
  max_orders_per_month: number | null;
  features: Record<string, unknown>;
  is_public: boolean;
  is_active: boolean;
  sort_order: number;
  subscriber_count: number;
  mrr: string;
}
