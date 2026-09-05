export type ProductUnit =
  "piece" | "kg" | "gram" | "liter" | "meter" | "pack" | "box";

export type PaymentMethod =
  "cash" | "card" | "mobile" | "bank_transfer" | "store_credit";

export type DiscountKind = "none" | "percent" | "fixed";

export interface Category {
  id: string;
  name: string;
  slug: string;
  color: string | null;
  image_url: string | null;
  sort_order: number;
  parent_id: string | null;
}

export interface Product {
  id: string;
  name: string;
  sku: string;
  barcode: string | null;
  category_id: string | null;
  unit: ProductUnit;
  price: string;
  image_url: string | null;
  track_stock: boolean;
  is_favorite: boolean;
  tax_rate: string;
  tax_inclusive: boolean;
  stock_quantity: string | null;
  low_stock: boolean;
}

export interface ProductLookup {
  product: Product;
  pack_size: string;
  matched_on: "barcode" | "sku" | "pack_barcode";
}

export interface OrderItem {
  id: string;
  product_id: string | null;
  product_name: string;
  sku: string | null;
  barcode: string | null;
  quantity: string;
  unit_price: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  tax_inclusive: boolean;
  line_total: string;
  refunded_quantity: string;
}

export interface OrderPayment {
  id: string;
  method: PaymentMethod;
  amount: string;
  tendered_amount: string | null;
  reference: string | null;
  card_last4: string | null;
}

export interface Order {
  id: string;
  order_number: string;
  status: string;
  branch_id: string;
  cashier_id: string | null;
  customer_id: string | null;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  rounding_adjustment: string;
  total: string;
  paid_total: string;
  change_due: string;
  refunded_total: string;
  currency: string;
  note: string | null;
  completed_at: string | null;
  created_at: string;
  items: OrderItem[];
  payments: OrderPayment[];
}

export interface Receipt {
  order: Order;
  shop: {
    name: string;
    branch_name: string;
    address: string | null;
    phone: string | null;
    tax_number: string | null;
    header: string | null;
    footer: string | null;
    currency: string;
    locale: string;
  };
  cashier_name: string | null;
  customer_name: string | null;
  printed_at: string;
}

export interface Shift {
  id: string;
  branch_id: string;
  user_id: string;
  status: "open" | "closed";
  opened_at: string;
  closed_at: string | null;
  opening_float: string;
  expected_cash: string;
  counted_cash: string | null;
  cash_difference: string | null;
  note: string | null;
}

export interface ShiftSummary {
  shift: Shift;
  order_count: number;
  gross_sales: string;
  cash_sales: string;
  card_sales: string;
  refund_total: string;
}
