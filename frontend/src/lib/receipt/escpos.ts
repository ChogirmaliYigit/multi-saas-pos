/**
 * ESC/POS command builder.
 *
 * Thermal printers do not speak HTML or PDF -- they consume a byte stream of
 * escape sequences interleaved with text. This encodes that stream for the
 * Epson-compatible command set that virtually every 58mm/80mm printer
 * implements.
 */

const ESC = 0x1b;
const GS = 0x1d;
const LF = 0x0a;

export type Align = "left" | "center" | "right";

/** Characters per line. The two standard paper widths at Font A. */
export const PAPER_COLUMNS = { "58": 32, "80": 48 } as const;
export type PaperWidth = keyof typeof PAPER_COLUMNS;

export class EscPosBuilder {
  private readonly chunks: number[] = [];
  readonly columns: number;

  constructor(paper: PaperWidth = "80") {
    this.columns = PAPER_COLUMNS[paper];
    // ESC @ -- reset. Printers keep state between jobs, so a receipt that
    // does not reset inherits whatever the last one left behind (still bold,
    // still double-height, still centred).
    this.raw(ESC, 0x40);
    // ESC t 0 -- code page 437, which matches the encoder below.
    this.raw(ESC, 0x74, 0x00);
  }

  private raw(...bytes: number[]): this {
    this.chunks.push(...bytes);
    return this;
  }

  /**
   * CP437, the default code page on essentially all thermal printers.
   * Anything outside it degrades to '?' rather than printing mojibake --
   * a receipt with a wrong character is confusing; one with a broken byte
   * stream can jam the printer.
   */
  text(value: string): this {
    for (const char of value) {
      const code = char.codePointAt(0) ?? 63;
      this.chunks.push(code < 0x80 ? code : (CP437[char] ?? 63));
    }
    return this;
  }

  line(value = ""): this {
    return this.text(value).raw(LF);
  }

  align(mode: Align): this {
    return this.raw(ESC, 0x61, { left: 0, center: 1, right: 2 }[mode]);
  }

  bold(on: boolean): this {
    return this.raw(ESC, 0x45, on ? 1 : 0);
  }

  /** Double width and/or height, for the shop name and the total. */
  size(width: 1 | 2, height: 1 | 2): this {
    return this.raw(GS, 0x21, ((width - 1) << 4) | (height - 1));
  }

  underline(on: boolean): this {
    return this.raw(ESC, 0x2d, on ? 1 : 0);
  }

  feed(lines = 1): this {
    return this.raw(ESC, 0x64, lines);
  }

  rule(char = "-"): this {
    return this.line(char.repeat(this.columns));
  }

  /**
   * Two columns filled to the paper width -- the backbone of a receipt.
   * Truncates the label rather than wrapping, because a wrapped label pushes
   * the amount onto its own line and the column stops lining up.
   */
  columnsLine(left: string, right: string): this {
    const space = Math.max(0, this.columns - right.length - 1);
    const label = left.length > space ? `${left.slice(0, space - 1)}…` : left;
    const padding = " ".repeat(
      Math.max(1, this.columns - label.length - right.length),
    );
    return this.line(`${label}${padding}${right}`);
  }

  /** Wraps at the paper width, breaking on spaces where possible. */
  wrapped(value: string): this {
    const words = value.split(/\s+/);
    let current = "";
    for (const word of words) {
      if (current && current.length + word.length + 1 > this.columns) {
        this.line(current);
        current = word;
      } else {
        current = current ? `${current} ${word}` : word;
      }
    }
    if (current) this.line(current);
    return this;
  }

  /**
   * Cut the paper. GS V 66 is a *partial* cut with feed: it leaves a small
   * tab so the receipt stays attached until the customer takes it, instead of
   * dropping on the floor.
   */
  cut(): this {
    return this.feed(3).raw(GS, 0x56, 66, 0x00);
  }

  /** Pop the cash drawer. Wired through the printer's RJ11 port. */
  openDrawer(): this {
    return this.raw(ESC, 0x70, 0x00, 0x19, 0xfa);
  }

  build(): Uint8Array {
    return new Uint8Array(this.chunks);
  }
}

/** The handful of CP437 mappings a receipt realistically needs. */
const CP437: Record<string, number> = {
  "£": 0x9c,
  "¥": 0x9d,
  "₧": 0x9e,
  ƒ: 0x9f,
  "€": 0xee,
  ä: 0x84,
  ö: 0x94,
  ü: 0x81,
  ß: 0xe1,
  Ä: 0x8e,
  Ö: 0x99,
  Ü: 0x9a,
  é: 0x82,
  è: 0x8a,
  ê: 0x88,
  à: 0x85,
  â: 0x83,
  ç: 0x87,
  ñ: 0xa4,
  Ñ: 0xa5,
  á: 0xa0,
  í: 0xa1,
  ó: 0xa2,
  ú: 0xa3,
  "°": 0xf8,
  "±": 0xf1,
  "·": 0xfa,
  "…": 0x2e,
};
