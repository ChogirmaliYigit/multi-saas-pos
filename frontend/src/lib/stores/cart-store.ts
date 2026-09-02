"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { DiscountKind, Product } from "@/lib/api/pos-types";
import {
  type Cents,
  type Milli,
  fromCents,
  lineGross,
  percentOf,
  taxFrom,
  toCents,
  toMilli,
} from "@/lib/pos/money";

export interface CartLine {
  /** Stable key for list rendering and quantity edits. */
  key: string;
  productId: string;
  name: string;
  sku: string;
  barcode: string | null;
  unit: Product["unit"];
  unitPriceCents: Cents;
  quantityMilli: Milli;
  taxRate: number;
  taxInclusive: boolean;
  discountKind: DiscountKind;
  discountValue: number;
  /** Null when the product is not stock-tracked. */
  stockAvailable: number | null;
}

export interface CartTotals {
  subtotal: Cents;
  discountTotal: Cents;
  taxTotal: Cents;
  total: Cents;
  itemCount: number;
}

interface CartState {
  lines: CartLine[];
  orderDiscountKind: DiscountKind;
  orderDiscountValue: number;
  customerId: string | null;
  note: string;
  /**
   * Regenerated after every completed sale. Sent with checkout so a retry
   * over a flaky connection cannot charge the customer twice.
   */
  idempotencyKey: string;
  selectedKey: string | null;

  addProduct: (product: Product, quantity?: number) => void;
  setQuantity: (key: string, quantityMilli: Milli) => void;
  adjustQuantity: (key: string, deltaMilli: Milli) => void;
  removeLine: (key: string) => void;
  setLineDiscount: (key: string, kind: DiscountKind, value: number) => void;
  setOrderDiscount: (kind: DiscountKind, value: number) => void;
  setCustomer: (customerId: string | null) => void;
  setNote: (note: string) => void;
  select: (key: string | null) => void;
  clear: () => void;
}

function newKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

export const useCartStore = create<CartState>()(
  persist(
    (set, get) => ({
      lines: [],
      orderDiscountKind: "none",
      orderDiscountValue: 0,
      customerId: null,
      note: "",
      idempotencyKey: newKey(),
      selectedKey: null,

      addProduct: (product, quantity = 1) => {
        const quantityMilli = toMilli(quantity);
        const existing = get().lines.find((l) => l.productId === product.id);

        // Scanning the same item twice bumps the quantity rather than adding a
        // second line -- a 30-item basket of duplicates is unreadable.
        if (existing) {
          set((state) => ({
            lines: state.lines.map((line) =>
              line.key === existing.key
                ? { ...line, quantityMilli: line.quantityMilli + quantityMilli }
                : line,
            ),
            selectedKey: existing.key,
          }));
          return;
        }

        const key = newKey();
        set((state) => ({
          lines: [
            ...state.lines,
            {
              key,
              productId: product.id,
              name: product.name,
              sku: product.sku,
              barcode: product.barcode,
              unit: product.unit,
              unitPriceCents: toCents(product.price),
              quantityMilli,
              taxRate: Number.parseFloat(product.tax_rate) || 0,
              taxInclusive: product.tax_inclusive,
              discountKind: "none",
              discountValue: 0,
              stockAvailable: product.track_stock
                ? Number.parseFloat(product.stock_quantity ?? "0")
                : null,
            },
          ],
          selectedKey: key,
        }));
      },

      setQuantity: (key, quantityMilli) =>
        set((state) => ({
          lines:
            quantityMilli <= 0
              ? state.lines.filter((line) => line.key !== key)
              : state.lines.map((line) =>
                  line.key === key ? { ...line, quantityMilli } : line,
                ),
        })),

      adjustQuantity: (key, deltaMilli) => {
        const line = get().lines.find((l) => l.key === key);
        if (!line) return;
        get().setQuantity(key, line.quantityMilli + deltaMilli);
      },

      removeLine: (key) =>
        set((state) => ({
          lines: state.lines.filter((line) => line.key !== key),
          selectedKey: state.selectedKey === key ? null : state.selectedKey,
        })),

      setLineDiscount: (key, kind, value) =>
        set((state) => ({
          lines: state.lines.map((line) =>
            line.key === key
              ? { ...line, discountKind: kind, discountValue: value }
              : line,
          ),
        })),

      setOrderDiscount: (kind, value) =>
        set({ orderDiscountKind: kind, orderDiscountValue: value }),

      setCustomer: (customerId) => set({ customerId }),
      setNote: (note) => set({ note }),
      select: (selectedKey) => set({ selectedKey }),

      clear: () =>
        set({
          lines: [],
          orderDiscountKind: "none",
          orderDiscountValue: 0,
          customerId: null,
          note: "",
          selectedKey: null,
          // New key: the next sale is a new sale.
          idempotencyKey: newKey(),
        }),
    }),
    {
      name: "pos-cart",
      // Survives an accidental refresh or a browser crash mid-basket, which
      // on a busy till is the difference between a pause and re-scanning
      // thirty items in front of a queue.
      partialize: (state) => ({
        lines: state.lines,
        orderDiscountKind: state.orderDiscountKind,
        orderDiscountValue: state.orderDiscountValue,
        customerId: state.customerId,
        note: state.note,
        idempotencyKey: state.idempotencyKey,
      }),
    },
  ),
);

/**
 * Preview totals, mirroring `app/services/pricing.py` step for step: line
 * discount, then order discount allocated across lines, then tax per line.
 * The server's answer is authoritative at checkout.
 */
export function computeTotals(
  lines: CartLine[],
  orderDiscountKind: DiscountKind,
  orderDiscountValue: number,
): CartTotals {
  const computed = lines.map((line) => {
    const gross = lineGross(line.unitPriceCents, line.quantityMilli);
    let discount = 0;
    if (line.discountKind === "percent") {
      discount = percentOf(gross, line.discountValue);
    } else if (line.discountKind === "fixed") {
      discount = Math.min(Math.max(toCents(line.discountValue), 0), gross);
    }
    return { line, gross, discount, net: gross - discount, tax: 0 };
  });

  const netAfterLines = computed.reduce((sum, c) => sum + c.net, 0);

  let orderDiscount = 0;
  if (orderDiscountKind === "percent") {
    orderDiscount = percentOf(netAfterLines, orderDiscountValue);
  } else if (orderDiscountKind === "fixed") {
    orderDiscount = Math.min(
      Math.max(toCents(orderDiscountValue), 0),
      netAfterLines,
    );
  }

  if (orderDiscount > 0 && netAfterLines > 0) {
    let allocated = 0;
    const shares = computed.map((c) =>
      Math.round((orderDiscount * c.net) / netAfterLines),
    );
    allocated = shares.reduce((a, b) => a + b, 0);
    // Push the rounding remainder onto the largest line, exactly as the
    // server does, so preview and receipt agree to the cent.
    const remainder = orderDiscount - allocated;
    if (remainder !== 0 && computed.length > 0) {
      let biggest = 0;
      computed.forEach((c, i) => {
        if (c.net > computed[biggest].net) biggest = i;
      });
      shares[biggest] += remainder;
    }
    computed.forEach((c, i) => {
      c.discount += shares[i];
      c.net -= shares[i];
    });
  }

  computed.forEach((c) => {
    c.tax = taxFrom(c.net, c.line.taxRate, c.line.taxInclusive);
  });

  const subtotal = computed.reduce((sum, c) => sum + c.gross, 0);
  const discountTotal = computed.reduce((sum, c) => sum + c.discount, 0);
  const taxTotal = computed.reduce((sum, c) => sum + c.tax, 0);
  const net = computed.reduce((sum, c) => sum + c.net, 0);
  const exclusiveTax = computed.reduce(
    (sum, c) => sum + (c.line.taxInclusive ? 0 : c.tax),
    0,
  );

  return {
    subtotal,
    discountTotal,
    taxTotal,
    total: net + exclusiveTax,
    itemCount: lines.reduce((sum, l) => sum + l.quantityMilli, 0) / 1000,
  };
}

export function lineTotalCents(line: CartLine): Cents {
  const gross = lineGross(line.unitPriceCents, line.quantityMilli);
  if (line.discountKind === "percent") {
    return gross - percentOf(gross, line.discountValue);
  }
  if (line.discountKind === "fixed") {
    return gross - Math.min(Math.max(toCents(line.discountValue), 0), gross);
  }
  return gross;
}

export function formatQuantity(line: CartLine): string {
  return line.quantityMilli % 1000 === 0
    ? String(line.quantityMilli / 1000)
    : (line.quantityMilli / 1000).toFixed(3);
}

export { fromCents };
