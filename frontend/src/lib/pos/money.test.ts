import { describe, expect, it } from "vitest";

import {
  fromCents,
  fromMilli,
  lineGross,
  percentOf,
  taxFrom,
  toCents,
  toMilli,
} from "./money";

describe("integer money", () => {
  it("does not accumulate float error", () => {
    // The reason this module exists: 0.1 + 0.2 !== 0.3 in a double.
    let cents = 0;
    for (let i = 0; i < 10; i += 1) cents += toCents("0.1");
    expect(fromCents(cents)).toBe("1.00");
  });

  it("round-trips awkward values", () => {
    for (const value of ["0.01", "1.20", "19.99", "1234.56", "0.00"]) {
      expect(fromCents(toCents(value))).toBe(value);
    }
  });

  it("formats negative amounts with the sign outside", () => {
    expect(fromCents(-1999)).toBe("-19.99");
  });

  it("pads the minor unit", () => {
    expect(fromCents(5)).toBe("0.05");
    expect(fromCents(50)).toBe("0.50");
  });
});

describe("quantities", () => {
  it("keeps three decimals for weighed goods", () => {
    expect(fromMilli(toMilli("0.256"))).toBe("0.256");
  });

  it("renders whole units without decimals", () => {
    expect(fromMilli(toMilli(3))).toBe("3");
  });
});

describe("line totals", () => {
  it("multiplies price by a fractional quantity", () => {
    // 256 g at 4.00/kg = 1.024 -> 1.02
    expect(lineGross(toCents("4.00"), toMilli("0.256"))).toBe(102);
  });

  it("multiplies price by a whole quantity exactly", () => {
    expect(lineGross(toCents("1.20"), toMilli(24))).toBe(2880);
  });
});

describe("discounts", () => {
  it("computes a percentage", () => {
    expect(percentOf(10000, 10)).toBe(1000);
  });

  it("clamps out-of-range percentages", () => {
    expect(percentOf(10000, 250)).toBe(10000);
    expect(percentOf(10000, -5)).toBe(0);
  });
});

describe("tax", () => {
  it("adds exclusive tax on top", () => {
    expect(taxFrom(1000, 0.2, false)).toBe(200);
  });

  it("extracts inclusive tax from within", () => {
    // 12.00 inclusive at 20% is 10.00 net + 2.00 tax.
    expect(taxFrom(1200, 0.2, true)).toBe(200);
  });

  it("is zero when there is no rate", () => {
    expect(taxFrom(1200, 0, true)).toBe(0);
  });
});
