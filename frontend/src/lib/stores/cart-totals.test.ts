import { describe, expect, it } from "vitest";

import { type CartLine, computeTotals } from "./cart-store";
import { fromCents, toCents, toMilli } from "@/lib/pos/money";

/**
 * The client previews cart totals so the screen updates instantly; the server
 * recomputes them at checkout and its answer is authoritative. These cases
 * are pinned to figures produced by the backend suite
 * (`tests/test_pricing.py`, `tests/test_pos.py`) -- if the two ever drift, a
 * cashier watches the total change at the moment they take payment.
 */
function line(overrides: Partial<CartLine> = {}): CartLine {
  return {
    key: Math.random().toString(),
    productId: "p",
    name: "Item",
    sku: "SKU",
    barcode: null,
    unit: "piece",
    unitPriceCents: toCents("10.00"),
    quantityMilli: toMilli(1),
    taxRate: 0,
    taxInclusive: false,
    discountKind: "none",
    discountValue: 0,
    stockAvailable: null,
    ...overrides,
  };
}

describe("cart preview totals", () => {
  it("matches the server for a plain basket", () => {
    const totals = computeTotals(
      [
        line({ unitPriceCents: toCents("2.50"), quantityMilli: toMilli(3) }),
        line({ unitPriceCents: toCents("1.20"), quantityMilli: toMilli(2) }),
      ],
      "none",
      0,
    );
    expect(fromCents(totals.subtotal)).toBe("9.90");
    expect(fromCents(totals.total)).toBe("9.90");
  });

  it("adds exclusive tax on top", () => {
    const totals = computeTotals([line({ taxRate: 0.2 })], "none", 0);
    expect(fromCents(totals.taxTotal)).toBe("2.00");
    expect(fromCents(totals.total)).toBe("12.00");
  });

  it("extracts inclusive tax without changing what is paid", () => {
    const totals = computeTotals(
      [
        line({
          unitPriceCents: toCents("12.00"),
          taxRate: 0.2,
          taxInclusive: true,
        }),
      ],
      "none",
      0,
    );
    expect(fromCents(totals.taxTotal)).toBe("2.00");
    expect(fromCents(totals.total)).toBe("12.00");
  });

  it("reproduces the mixed-rate basket verified end to end", () => {
    // 24 cola @ 1.20 inclusive-20%, plus a zero-rated croissant.
    // The live terminal and the recorded order both showed 30.40 / 4.80.
    const totals = computeTotals(
      [
        line({
          unitPriceCents: toCents("1.20"),
          quantityMilli: toMilli(24),
          taxRate: 0.2,
          taxInclusive: true,
        }),
        line({ unitPriceCents: toCents("1.60"), taxRate: 0, taxInclusive: true }),
      ],
      "none",
      0,
    );
    expect(fromCents(totals.total)).toBe("30.40");
    expect(fromCents(totals.taxTotal)).toBe("4.80");
  });

  it("taxes the discounted amount, not the shelf price", () => {
    const totals = computeTotals(
      [
        line({
          unitPriceCents: toCents("100.00"),
          taxRate: 0.1,
          discountKind: "percent",
          discountValue: 10,
        }),
      ],
      "none",
      0,
    );
    expect(fromCents(totals.discountTotal)).toBe("10.00");
    expect(fromCents(totals.taxTotal)).toBe("9.00");
    expect(fromCents(totals.total)).toBe("99.00");
  });

  it("never loses a cent when allocating an order discount", () => {
    // Three equal lines and 10.00 off: 3.33 each strands 0.01 somewhere.
    const totals = computeTotals([line(), line(), line()], "fixed", 10);
    expect(fromCents(totals.discountTotal)).toBe("10.00");
    expect(fromCents(totals.total)).toBe("20.00");
  });

  it("allocates an order discount across differing tax rates", () => {
    const totals = computeTotals(
      [
        line({ unitPriceCents: toCents("100.00"), taxRate: 0.2 }),
        line({ unitPriceCents: toCents("100.00"), taxRate: 0.05 }),
      ],
      "percent",
      10,
    );
    // 90 * 0.20 + 90 * 0.05 = 22.50
    expect(fromCents(totals.taxTotal)).toBe("22.50");
    expect(fromCents(totals.total)).toBe("202.50");
  });

  it("caps a fixed line discount at the line value", () => {
    const totals = computeTotals(
      [
        line({
          unitPriceCents: toCents("5.00"),
          discountKind: "fixed",
          discountValue: 500,
        }),
      ],
      "none",
      0,
    );
    expect(fromCents(totals.total)).toBe("0.00");
  });

  it("counts weighed quantities as fractions of a unit", () => {
    const totals = computeTotals(
      [line({ unitPriceCents: toCents("4.00"), quantityMilli: toMilli("0.256") })],
      "none",
      0,
    );
    expect(fromCents(totals.total)).toBe("1.02");
    expect(totals.itemCount).toBeCloseTo(0.256);
  });

  it("returns zero for an empty cart", () => {
    const totals = computeTotals([], "none", 0);
    expect(totals.total).toBe(0);
  });
});
