# POS terminal — Step 4

## Barcode capture

USB and Bluetooth scanners are keyboard emulators. There is no API to ask
"was that a scanner?", so the only available signal is timing, and the whole
design in `src/lib/pos/use-barcode-scanner.ts` follows from that:

| | Human typing | Scanner |
|---|---|---|
| Inter-key gap | 80–300 ms | 5–20 ms |

The threshold sits at **40 ms**, in the empty gap between the two
distributions. Keystrokes are buffered with timestamps; a gap wider than the
threshold discards the buffer, so ordinary typing never accumulates into a
phantom scan.

Three consequences worth stating, because each one is a bug if you get it
wrong:

1. **The listener is on `document`, capture phase.** A scan registers whatever
   has focus. A cashier should never have to click a search box first.
2. **`Enter` is only claimed when the burst was fast *and* long enough.**
   Otherwise `preventDefault` is not called and Enter still submits forms.
3. **It is disabled while a modal is open.** A scan landing in the cart behind
   the payment dialog would change the total the cashier is looking at.

Verified live in the browser: a synchronous 13-character burst added the item;
the same characters dispatched 120 ms apart added nothing and left `Enter`
uncancelled.

## Money never touches a float

`0.1 + 0.2 === 0.30000000000000004`. Cart maths runs in integer minor units
(`src/lib/pos/money.ts`) and only formats to a decimal string for display.

These figures are a **preview**. `app/services/pricing.py` recomputes every
total from its own prices at checkout and its answer wins. The two
implementations follow the same order of operations — line discount, then
order discount allocated across lines, then tax per line — because taxing
before discounting overcharges, and discounting after tax makes the tax line
on the receipt wrong, which is the number an audit looks at.

`src/lib/stores/cart-totals.test.ts` pins the preview to figures produced by
the backend suite. If they ever drift, the cashier watches the total change at
the moment they take payment.

## Prices are never sent from the client

`OrderItemIn` carries `product_id` and `quantity` and deliberately has no
`unit_price`. A client that could name its own price would be a discount
button with no permission check. Tested: a request with
`unit_price: "0.01"` is charged the shelf price.

Applying a discount is a separate permission (`order.discount`) from ringing
up a sale, because discounts are the usual route for shrinkage to leave
through the front door.

## Receipt printing: three transports

| Transport | Browsers | Notes |
|---|---|---|
| WebUSB | Chrome, Edge | Needs HTTPS + a user gesture; bulk OUT endpoint discovered, not hardcoded |
| Web Bluetooth | Chrome, Edge | Chunked to 20 bytes; writes awaited in order or the bytes interleave |
| Print dialog | All, incl. Safari/Firefox | `@page { size: 80mm auto }` lays out a continuous roll |

The print path is not really a fallback: Safari and Firefox have no WebUSB at
all, and the same dialog offers "Save as PDF" for emailing a copy. It uses a
hidden iframe rather than `window.open`, which popup blockers eat.

Both renderers are built from the **same** `/orders/{id}/receipt` payload, so
a reprint can never disagree with the paper the customer walked out with.

ESC/POS output always begins with `ESC @`. Printers keep state between jobs, so
a receipt that does not reset inherits whatever the last one left behind —
still bold, still double-height. Text is encoded to CP437 with `?` for
unmapped characters, because a wrong character is confusing but a broken byte
stream can jam the printer.

## Bugs found by testing this step

**Change was recorded as zero.** The terminal showed `$19.60` change on a
`$50.00` tender for a `$30.40` sale, but the order stored `change_due: 0.00` —
change was derived only from amounts that overshot the total, never from the
tendered note. The receipt would have printed no change line and the drawer
reconciliation would have been wrong. Change now comes from
`tendered - amount` per payment, `Payment.change_amount` is populated, and the
drawer counts the tendered note as what physically entered it.

**Auto-print threw a modal dialog after every sale.** With no direct printer
connected, auto-print fired the browser's print dialog, which blocks the whole
UI until dismissed — on every single sale. Auto-print now applies only to a
directly connected printer, where printing is silent; otherwise the completion
screen offers a Print button.

**The header claimed "Shift open" on the screen asking you to open a shift.**

## Verified end to end

Against real PostgreSQL and the real API, in a real browser:

- scanned `5449000000996` → Cola added, `$1.20` with `$0.20` inclusive VAT
- scanned the carton code `15449000000993` → added 24, merged into one line
- typed the same digits at human speed → nothing added, Enter still worked
- scanned an unknown code → clear error, nothing silently added
- mixed-rate basket (inclusive VAT + zero-rated) → `$30.40` total, `$4.80` tax
- paid with `$50.00` → `$19.60` change, drawer expected `$130.40`
- receipt rendered at 48 columns (80 mm) and 32 columns (58 mm)

Backend: **54 tests**. Frontend: **45 tests**. Lint, types and build clean on
both.
