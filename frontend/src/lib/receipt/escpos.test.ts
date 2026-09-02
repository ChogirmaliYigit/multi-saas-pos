import { describe, expect, it } from "vitest";

import { EscPosBuilder, PAPER_COLUMNS } from "./escpos";

const decoder = new TextDecoder("ascii");

function asText(bytes: Uint8Array): string {
  return decoder.decode(bytes);
}

describe("EscPosBuilder", () => {
  it("always begins with a reset and a code page", () => {
    // Printers keep state between jobs; without ESC @ a receipt inherits the
    // last one's bold/double-height settings.
    const bytes = new EscPosBuilder("80").build();
    expect([...bytes.slice(0, 5)]).toEqual([0x1b, 0x40, 0x1b, 0x74, 0x00]);
  });

  it("uses the right column count per paper width", () => {
    expect(new EscPosBuilder("58").columns).toBe(PAPER_COLUMNS["58"]);
    expect(new EscPosBuilder("80").columns).toBe(48);
  });

  it("pads two-column lines to exactly the paper width", () => {
    const bytes = new EscPosBuilder("58").columnsLine("Subtotal", "9.90").build();
    const line = asText(bytes)
      .split("\n")[0]
      .replace(/^\x1b@\x1bt\x00/, "");
    expect(line).toHaveLength(32);
    expect(line.startsWith("Subtotal")).toBe(true);
    expect(line.endsWith("9.90")).toBe(true);
  });

  it("truncates a long label rather than wrapping it", () => {
    // A wrapped label pushes the amount onto its own line and the column
    // stops lining up down the receipt.
    const bytes = new EscPosBuilder("58")
      .columnsLine("Extremely long product name that will not fit", "12.34")
      .build();
    const line = asText(bytes)
      .split("\n")[0]
      .replace(/^\x1b@\x1bt\x00/, "");
    expect(line).toHaveLength(32);
    expect(line.endsWith("12.34")).toBe(true);
  });

  it("wraps body text on word boundaries", () => {
    const bytes = new EscPosBuilder("58")
      .wrapped("Thank you for shopping with us today at the corner store")
      .build();
    const lines = asText(bytes)
      .replace(/^\x1b@\x1bt\x00/, "")
      .split("\n")
      .filter(Boolean);
    expect(lines.length).toBeGreaterThan(1);
    for (const line of lines) expect(line.length).toBeLessThanOrEqual(32);
  });

  it("emits a partial cut so the receipt stays attached", () => {
    const bytes = new EscPosBuilder("80").cut().build();
    const tail = [...bytes.slice(-4)];
    expect(tail).toEqual([0x1d, 0x56, 66, 0x00]);
  });

  it("emits the drawer kick pulse", () => {
    const bytes = new EscPosBuilder("80").openDrawer().build();
    expect([...bytes.slice(-5)]).toEqual([0x1b, 0x70, 0x00, 0x19, 0xfa]);
  });

  it("maps non-ASCII to CP437 instead of emitting broken bytes", () => {
    const bytes = new EscPosBuilder("80").text("café £5").build();
    // Every byte must be a single 8-bit value; UTF-8 multibyte would jam the
    // printer or print mojibake.
    expect(bytes.every((b) => b <= 0xff)).toBe(true);
    expect([...bytes]).toContain(0x82); // é
    expect([...bytes]).toContain(0x9c); // £
  });

  it("substitutes a question mark for characters with no mapping", () => {
    const bytes = new EscPosBuilder("80").text("日本").build();
    const body = [...bytes.slice(5)];
    expect(body).toEqual([63, 63]);
  });
});
