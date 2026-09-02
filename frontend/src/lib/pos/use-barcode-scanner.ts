"use client";

import { useEffect, useRef } from "react";

export interface BarcodeScannerOptions {
  onScan: (code: string) => void;
  /**
   * Max milliseconds between keystrokes for input to count as a scan.
   * Human typing is 80-300ms per character; scanners emit 5-20ms. 40ms sits
   * in the empty gap between the two distributions.
   */
  maxIntervalMs?: number;
  /** Shorter bursts are almost always a human hitting a shortcut. */
  minLength?: number;
  enabled?: boolean;
}

const TERMINATORS = new Set(["Enter", "Tab"]);

/**
 * Captures USB/Bluetooth barcode scanners.
 *
 * These devices are keyboard emulators: they "type" the code and press Enter.
 * There is no API to ask "was that a scanner?", so the only signal available
 * is timing, and the whole design follows from that:
 *
 *  - Keystrokes are buffered with timestamps. A gap longer than
 *    `maxIntervalMs` discards the buffer and starts fresh, so ordinary typing
 *    never accumulates into a phantom scan.
 *  - Enter only counts as a scan terminator if the buffer was filled fast
 *    *and* is long enough. Otherwise the key is left alone, so pressing Enter
 *    in a form still submits it.
 *  - The listener is on `document` in the capture phase, so a scan registers
 *    no matter which element has focus. That is the point: a cashier should
 *    never have to click a search box first.
 *  - When focus is in a text field, a real scan is still captured, but
 *    `preventDefault` runs only once the burst is confirmed -- so the digits
 *    may briefly appear in the field and are then cleared by the caller.
 */
export function useBarcodeScanner({
  onScan,
  maxIntervalMs = 40,
  minLength = 4,
  enabled = true,
}: BarcodeScannerOptions): void {
  const buffer = useRef("");
  const lastKeyAt = useRef(0);
  // Kept in a ref so re-renders never detach and reattach the listener --
  // a dropped keystroke mid-scan would corrupt the code. Written in an
  // effect, never during render.
  const handler = useRef(onScan);
  useEffect(() => {
    handler.current = onScan;
  }, [onScan]);

  useEffect(() => {
    if (!enabled) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey) return;

      const now = performance.now();
      const gap = now - lastKeyAt.current;
      lastKeyAt.current = now;

      if (TERMINATORS.has(event.key)) {
        const code = buffer.current;
        buffer.current = "";
        // Only claim the keypress when this really looks like a scan;
        // otherwise Enter must keep working as Enter.
        if (code.length >= minLength && gap <= maxIntervalMs) {
          event.preventDefault();
          event.stopPropagation();
          handler.current(code);
        }
        return;
      }

      // Printable characters only. Scanners emit digits and the odd letter;
      // modifiers, arrows and function keys are not part of a code.
      if (event.key.length !== 1) return;

      if (gap > maxIntervalMs) {
        buffer.current = event.key;
        return;
      }
      buffer.current += event.key;
    }

    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [enabled, maxIntervalMs, minLength]);
}
