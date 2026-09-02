import { describe, expect, it } from "vitest";

import type { Receipt } from "@/lib/api/pos-types";

import fixture from "./__fixtures__/receipt.json";
import { buildReceiptBytes } from "./build-receipt";
import { receiptHtml } from "./print-pdf";

/**
 * The fixture is a real /orders/{id}/receipt response captured from the
 * running API: 24 cola at 1.20 (VAT 20% inclusive) plus a zero-rated
 * croissant, paid with a 50.00 note.
 */
const receipt = fixture as unknown as Receipt;

/** Strip ESC/POS control sequences so the printed text layout can be read. */
function renderedLines(bytes: Uint8Array): string[] {
  const out: string[] = [];
  let line: number[] = [];
  for (let i = 0; i < bytes.length; i += 1) {
    const byte = bytes[i];
    if (byte === 0x1b) {
      // ESC: @ and - and E and a and d take one operand; t takes one.
      i += bytes[i + 1] === 0x70 ? 4 : 2;
      continue;
    }
    if (byte === 0x1d) {
      i += bytes[i + 1] === 0x56 ? 3 : 2; // GS V (cut) vs GS ! (size)
      continue;
    }
    if (byte === 0x0a) {
      out.push(String.fromCharCode(...line));
      line = [];
      continue;
    }
    line.push(byte);
  }
  if (line.length) out.push(String.fromCharCode(...line));
  return out;
}

describe("ESC/POS receipt", () => {
  const lines = renderedLines(buildReceiptBytes(receipt, "80"));
  const text = lines.join("\n");

  it("prints the shop name and receipt number", () => {
    expect(text).toContain("Corner Store");
    expect(text).toContain(receipt.order.order_number);
  });

  it("prints every line item with quantity and price", () => {
    expect(text).toContain("Cola 330ml can");
    expect(text).toContain("24 x $1.20");
    expect(text).toContain("Croissant");
  });

  it("labels inclusive tax so the customer does not add it on again", () => {
    expect(text).toContain("Tax (incl.)");
    expect(text).toContain("$4.80");
  });

  it("prints the total and the change", () => {
    expect(text).toContain("TOTAL");
    expect(text).toContain("$30.40");
    expect(text).toContain("Change");
    expect(text).toContain("$19.60");
  });

  it("aligns amounts to the right edge of the paper", () => {
    const subtotal = lines.find((l) => l.startsWith("Subtotal"));
    expect(subtotal).toBeDefined();
    expect(subtotal).toHaveLength(48);
    expect(subtotal!.endsWith("$30.40")).toBe(true);
  });

  it("draws rules the full paper width", () => {
    const rules = lines.filter((l) => /^-+$/.test(l));
    expect(rules.length).toBeGreaterThan(2);
    for (const rule of rules) expect(rule).toHaveLength(48);
  });

  it("narrows to 32 columns on 58mm paper", () => {
    const narrow = renderedLines(buildReceiptBytes(receipt, "58"));
    const subtotal = narrow.find((l) => l.startsWith("Subtotal"));
    expect(subtotal).toHaveLength(32);
  });

  it("marks a reprint so a duplicate is not mistaken for a second sale", () => {
    const copy = renderedLines(buildReceiptBytes(receipt, "80", { copy: true }));
    expect(copy.join("\n")).toContain("*** REPRINT ***");
  });

  it("appends the drawer kick only when asked", () => {
    const withDrawer = buildReceiptBytes(receipt, "80", { openDrawer: true });
    const without = buildReceiptBytes(receipt, "80", { openDrawer: false });
    expect(withDrawer.length).toBeGreaterThan(without.length);
  });
});

describe("PDF receipt", () => {
  const html = receiptHtml(receipt, 80);

  it("sizes the page to the paper roll", () => {
    // `size: 80mm auto` is what makes the browser lay out a continuous roll
    // rather than paginating onto A4.
    expect(html).toContain("@page { size: 80mm auto; margin: 0; }");
    expect(html).toContain("width: 72mm");
  });

  it("narrows the printable width for 58mm", () => {
    expect(receiptHtml(receipt, 58)).toContain("width: 48mm");
  });

  it("shows the same figures as the thermal output", () => {
    expect(html).toContain("$30.40");
    expect(html).toContain("$4.80");
    expect(html).toContain("$19.60");
    expect(html).toContain(receipt.order.order_number);
  });

  it("escapes shop and product text", () => {
    const hostile = {
      ...receipt,
      shop: { ...receipt.shop, name: '<script>alert("x")</script>' },
    } as Receipt;
    const rendered = receiptHtml(hostile, 80);
    expect(rendered).not.toContain("<script>alert");
    expect(rendered).toContain("&lt;script&gt;");
  });
});
