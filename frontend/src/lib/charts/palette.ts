/**
 * Chart colour tokens.
 *
 * These are not picked by eye. The set was run through the data-viz
 * validator (`scripts/validate_palette.js`) in both modes and clears every
 * gate: lightness band, chroma floor, colour-blind separation, normal-vision
 * separation, and 3:1 contrast against the chart surface.
 *
 *   light  #0d9488 · #eb6834 · #2a78d6   worst adjacent CVD ΔE 10.7, normal 27.5
 *   dark   #10a396 · #d95926 · #3987e5   worst adjacent CVD ΔE 13.5, normal 26.5
 *
 * Slot 1 is the brand teal, so a single-series chart reads as part of the
 * product rather than a bolted-on widget. Three slots is the cap: the
 * validated palette only clears the all-pairs floors for the first three, and
 * the only categorical chart here (payment methods) has exactly three.
 *
 * Hues are assigned in fixed order and never cycled. Colour follows the
 * entity, not its rank -- filtering a series out must not repaint the others.
 */

export const SERIES = {
  1: "var(--chart-series-1)",
  2: "var(--chart-series-2)",
  3: "var(--chart-series-3)",
} as const;

/** Single-series magnitude (revenue, hourly takings, top products). */
export const PRIMARY_SERIES = SERIES[1];

/** Stable slot per payment method, so adding a method never recolours the rest. */
export const PAYMENT_COLORS: Record<string, string> = {
  cash: SERIES[1],
  card: SERIES[2],
  mobile: SERIES[3],
  bank_transfer: SERIES[3],
  store_credit: SERIES[3],
};

export const PAYMENT_LABELS: Record<string, string> = {
  cash: "Cash",
  card: "Card",
  mobile: "Mobile",
  bank_transfer: "Transfer",
  store_credit: "Store credit",
};
