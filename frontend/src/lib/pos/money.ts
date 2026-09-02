/**
 * Cart arithmetic in integer minor units.
 *
 * JavaScript numbers are IEEE-754 doubles: 0.1 + 0.2 === 0.30000000000000004.
 * Doing cart maths in floats produces totals that are a cent out, which the
 * customer notices before you do. Everything here works in whole cents and
 * only converts to a decimal string for display.
 *
 * These figures are a *preview*. The server recomputes every total from its
 * own prices at checkout (`app/services/pricing.py`) and its answer wins --
 * this exists so the cart updates instantly instead of after a round trip.
 */

export type Cents = number;

export function toCents(value: string | number): Cents {
  const n = typeof value === "string" ? Number.parseFloat(value) : value;
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 100);
}

export function fromCents(cents: Cents): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(Math.round(cents));
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

/** Quantities carry 3 decimals (weighed goods), held as thousandths. */
export type Milli = number;

export function toMilli(value: string | number): Milli {
  const n = typeof value === "string" ? Number.parseFloat(value) : value;
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 1000);
}

export function fromMilli(milli: Milli): string {
  const whole = milli / 1000;
  // Whole units display as "2", weighed ones as "0.256".
  return Number.isInteger(whole) ? String(whole) : whole.toFixed(3);
}

/** price(cents) * quantity(thousandths) -> cents, rounded half-up. */
export function lineGross(unitPriceCents: Cents, quantityMilli: Milli): Cents {
  return Math.round((unitPriceCents * quantityMilli) / 1000);
}

export function percentOf(amount: Cents, percent: number): Cents {
  return Math.round((amount * Math.min(Math.max(percent, 0), 100)) / 100);
}

/**
 * Extract tax from a tax-inclusive amount: tax = net - net / (1 + rate).
 * Mirrors `_tax_for` on the server.
 */
export function taxFrom(netCents: Cents, rate: number, inclusive: boolean): Cents {
  if (rate <= 0) return 0;
  if (inclusive) return Math.round(netCents - netCents / (1 + rate));
  return Math.round(netCents * rate);
}

export function formatCents(
  cents: Cents,
  currency: string,
  locale = "en-US",
): string {
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(
    cents / 100,
  );
}
