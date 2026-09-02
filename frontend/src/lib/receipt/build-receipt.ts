import type { Receipt } from "@/lib/api/pos-types";

import { EscPosBuilder, type PaperWidth } from "./escpos";

function formatMoney(value: string, currency: string, locale: string): string {
  const n = Number.parseFloat(value);
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    currencyDisplay: "narrowSymbol",
  }).format(Number.isFinite(n) ? n : 0);
}

function formatQuantity(value: string): string {
  const n = Number.parseFloat(value);
  return Number.isInteger(n) ? String(n) : n.toFixed(3);
}

/**
 * Render a receipt to ESC/POS bytes.
 *
 * Built from the same `Receipt` payload the PDF path uses, so a reprint can
 * never disagree with the paper the customer walked out with.
 */
export function buildReceiptBytes(
  receipt: Receipt,
  paper: PaperWidth = "80",
  options: { openDrawer?: boolean; copy?: boolean } = {},
): Uint8Array {
  const { order, shop } = receipt;
  const locale = shop.locale || "en-US";
  const currency = shop.currency || "USD";
  const cash = (value: string) => formatMoney(value, currency, locale);

  const b = new EscPosBuilder(paper);

  b.align("center").bold(true).size(2, 2).line(shop.name).size(1, 1).bold(false);
  if (shop.branch_name && shop.branch_name !== shop.name) b.line(shop.branch_name);
  if (shop.address) b.wrapped(shop.address);
  if (shop.phone) b.line(shop.phone);
  if (shop.tax_number) b.line(`Tax No: ${shop.tax_number}`);
  if (shop.header) b.feed(1).wrapped(shop.header);

  b.feed(1).align("left").rule();
  b.columnsLine("Receipt", order.order_number);
  b.columnsLine(
    "Date",
    new Intl.DateTimeFormat(locale, {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(order.completed_at ?? order.created_at)),
  );
  if (receipt.cashier_name) b.columnsLine("Served by", receipt.cashier_name);
  if (receipt.customer_name) b.columnsLine("Customer", receipt.customer_name);
  b.rule();

  for (const item of order.items) {
    b.line(item.product_name);
    const qty = formatQuantity(item.quantity);
    b.columnsLine(`  ${qty} x ${cash(item.unit_price)}`, cash(item.line_total));
    if (Number.parseFloat(item.discount_amount) > 0) {
      b.columnsLine("  Discount", `-${cash(item.discount_amount)}`);
    }
  }

  b.rule();
  b.columnsLine("Subtotal", cash(order.subtotal));
  if (Number.parseFloat(order.discount_total) > 0) {
    b.columnsLine("Discount", `-${cash(order.discount_total)}`);
  }
  if (Number.parseFloat(order.tax_total) > 0) {
    // Inclusive tax is inside the total already; say so, or the customer adds
    // it on and thinks the receipt is wrong.
    const inclusive = order.items.some((item) => item.tax_inclusive);
    b.columnsLine(inclusive ? "Tax (incl.)" : "Tax", cash(order.tax_total));
  }
  if (Number.parseFloat(order.rounding_adjustment) !== 0) {
    b.columnsLine("Rounding", cash(order.rounding_adjustment));
  }

  b.bold(true).size(2, 2);
  // Double-width halves the columns, so the total is laid out at that width.
  const wide = Math.floor(b.columns / 2);
  const totalText = cash(order.total);
  const label = "TOTAL";
  b.line(
    `${label}${" ".repeat(Math.max(1, wide - label.length - totalText.length))}${totalText}`,
  );
  b.size(1, 1).bold(false);

  b.rule();
  for (const payment of order.payments) {
    const method = payment.method.replace("_", " ");
    const suffix = payment.card_last4 ? ` ****${payment.card_last4}` : "";
    b.columnsLine(
      `${method[0].toUpperCase()}${method.slice(1)}${suffix}`,
      cash(payment.amount),
    );
  }
  if (Number.parseFloat(order.change_due) > 0) {
    b.columnsLine("Change", cash(order.change_due));
  }

  if (order.note) b.feed(1).wrapped(order.note);

  b.feed(1).align("center");
  if (options.copy) b.bold(true).line("*** REPRINT ***").bold(false);
  b.wrapped(shop.footer || "Thank you for your custom");
  b.feed(1).line(order.order_number);

  if (options.openDrawer) b.openDrawer();
  b.cut();

  return b.build();
}
