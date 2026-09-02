"use client";

import type { Receipt } from "@/lib/api/pos-types";

/**
 * The universal path: render the receipt as HTML sized to the paper and hand
 * it to the browser's print pipeline.
 *
 * `@page { size: 80mm auto }` makes the browser lay out a continuous roll,
 * which is exactly what a thermal printer expects -- and the same dialog
 * offers "Save as PDF", so this covers both "print on the thermal printer via
 * its OS driver" and "email the customer a copy" with one code path and no
 * PDF library in the bundle.
 *
 * Works in every browser, including the ones with no WebUSB.
 */

function money(value: string, currency: string, locale: string): string {
  const n = Number.parseFloat(value);
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(
    Number.isFinite(n) ? n : 0,
  );
}

function qty(value: string): string {
  const n = Number.parseFloat(value);
  return Number.isInteger(n) ? String(n) : n.toFixed(3);
}

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

export function receiptHtml(
  receipt: Receipt,
  paperMm: 58 | 80 = 80,
  options: { copy?: boolean } = {},
): string {
  const { order, shop } = receipt;
  const locale = shop.locale || "en-US";
  const currency = shop.currency || "USD";
  const cash = (v: string) => money(v, currency, locale);
  // 58mm rolls have ~48mm of printable width; 80mm have ~72mm.
  const contentMm = paperMm === 58 ? 48 : 72;

  const rows = order.items
    .map((item) => {
      const discount =
        Number.parseFloat(item.discount_amount) > 0
          ? `<div class="row muted"><span>Discount</span><span>-${cash(item.discount_amount)}</span></div>`
          : "";
      return `
        <div class="item">
          <div class="name">${escapeHtml(item.product_name)}</div>
          <div class="row"><span>${qty(item.quantity)} &times; ${cash(item.unit_price)}</span><span>${cash(item.line_total)}</span></div>
          ${discount}
        </div>`;
    })
    .join("");

  const payments = order.payments
    .map((payment) => {
      const method = payment.method.replace("_", " ");
      const last4 = payment.card_last4 ? ` ****${payment.card_last4}` : "";
      return `<div class="row"><span>${escapeHtml(method)}${last4}</span><span>${cash(payment.amount)}</span></div>`;
    })
    .join("");

  return `<!doctype html>
<html><head><meta charset="utf-8"><title>${escapeHtml(order.order_number)}</title>
<style>
  @page { size: ${paperMm}mm auto; margin: 0; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 3mm;
    width: ${contentMm}mm;
    /* Monospace keeps the amount column aligned, exactly as on the thermal
       printer's fixed-pitch font. */
    font-family: "Menlo", "Consolas", ui-monospace, monospace;
    font-size: ${paperMm === 58 ? "9.5px" : "11px"};
    line-height: 1.45;
    color: #000;
    background: #fff;
    -webkit-font-smoothing: none;
  }
  .center { text-align: center; }
  .shop { font-size: ${paperMm === 58 ? "14px" : "17px"}; font-weight: 700; }
  .rule { border-top: 1px dashed #000; margin: 2mm 0; }
  .row { display: flex; justify-content: space-between; gap: 4px; }
  .row span:last-child { white-space: nowrap; }
  .muted { opacity: 0.75; padding-left: 3mm; }
  .item { margin-bottom: 1.2mm; }
  .name { word-break: break-word; }
  .total { font-size: ${paperMm === 58 ? "13px" : "16px"}; font-weight: 700; }
  .copy { font-weight: 700; letter-spacing: 1px; }
  @media print { body { padding: 2mm; } }
</style></head>
<body>
  <div class="center">
    <div class="shop">${escapeHtml(shop.name)}</div>
    ${shop.branch_name && shop.branch_name !== shop.name ? `<div>${escapeHtml(shop.branch_name)}</div>` : ""}
    ${shop.address ? `<div>${escapeHtml(shop.address)}</div>` : ""}
    ${shop.phone ? `<div>${escapeHtml(shop.phone)}</div>` : ""}
    ${shop.tax_number ? `<div>Tax No: ${escapeHtml(shop.tax_number)}</div>` : ""}
    ${shop.header ? `<div>${escapeHtml(shop.header)}</div>` : ""}
  </div>
  <div class="rule"></div>
  <div class="row"><span>Receipt</span><span>${escapeHtml(order.order_number)}</span></div>
  <div class="row"><span>Date</span><span>${new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(order.completed_at ?? order.created_at))}</span></div>
  ${receipt.cashier_name ? `<div class="row"><span>Served by</span><span>${escapeHtml(receipt.cashier_name)}</span></div>` : ""}
  ${receipt.customer_name ? `<div class="row"><span>Customer</span><span>${escapeHtml(receipt.customer_name)}</span></div>` : ""}
  <div class="rule"></div>
  ${rows}
  <div class="rule"></div>
  <div class="row"><span>Subtotal</span><span>${cash(order.subtotal)}</span></div>
  ${Number.parseFloat(order.discount_total) > 0 ? `<div class="row"><span>Discount</span><span>-${cash(order.discount_total)}</span></div>` : ""}
  ${Number.parseFloat(order.tax_total) > 0 ? `<div class="row"><span>Tax${order.items.some((i) => i.tax_inclusive) ? " (incl.)" : ""}</span><span>${cash(order.tax_total)}</span></div>` : ""}
  ${Number.parseFloat(order.rounding_adjustment) !== 0 ? `<div class="row"><span>Rounding</span><span>${cash(order.rounding_adjustment)}</span></div>` : ""}
  <div class="row total"><span>TOTAL</span><span>${cash(order.total)}</span></div>
  <div class="rule"></div>
  ${payments}
  ${Number.parseFloat(order.change_due) > 0 ? `<div class="row"><span>Change</span><span>${cash(order.change_due)}</span></div>` : ""}
  ${order.note ? `<div class="rule"></div><div>${escapeHtml(order.note)}</div>` : ""}
  <div class="rule"></div>
  <div class="center">
    ${options.copy ? `<div class="copy">*** REPRINT ***</div>` : ""}
    <div>${escapeHtml(shop.footer || "Thank you for your custom")}</div>
    <div>${escapeHtml(order.order_number)}</div>
  </div>
</body></html>`;
}

/**
 * Print via a hidden iframe rather than window.open: popup blockers eat
 * `window.open` when it is not the direct result of a click, and a cashier
 * pressing "print" on the payment-complete screen is exactly that case.
 */
export function printReceiptPdf(
  receipt: Receipt,
  paperMm: 58 | 80 = 80,
  options: { copy?: boolean } = {},
): void {
  const iframe = document.createElement("iframe");
  iframe.setAttribute("aria-hidden", "true");
  iframe.style.cssText =
    "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
  document.body.appendChild(iframe);

  const doc = iframe.contentWindow?.document;
  if (!doc) {
    iframe.remove();
    return;
  }

  doc.open();
  doc.write(receiptHtml(receipt, paperMm, options));
  doc.close();

  const run = () => {
    iframe.contentWindow?.focus();
    iframe.contentWindow?.print();
    // Removing the iframe synchronously cancels the print in some browsers.
    window.setTimeout(() => iframe.remove(), 1000);
  };

  if (doc.readyState === "complete") run();
  else iframe.onload = run;
}

/** Offer the receipt as a downloadable HTML file, for emailing on. */
export function receiptBlob(receipt: Receipt, paperMm: 58 | 80 = 80): Blob {
  return new Blob([receiptHtml(receipt, paperMm)], { type: "text/html" });
}
