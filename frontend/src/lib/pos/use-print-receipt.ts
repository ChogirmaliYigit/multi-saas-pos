"use client";

import { useCallback } from "react";
import { toast } from "sonner";

import type { Receipt } from "@/lib/api/pos-types";
import { buildReceiptBytes } from "@/lib/receipt/build-receipt";
import { printReceiptPdf } from "@/lib/receipt/print-pdf";
import { usePrinterStore } from "@/lib/stores/printer-store";

/**
 * One call site for printing, whichever transport is configured.
 *
 * If a direct printer is connected but errors mid-job (out of paper, cable
 * pulled), it falls back to the print dialog rather than losing the receipt.
 * The customer is standing there either way.
 */
export function usePrintReceipt() {
  const transport = usePrinterStore((s) => s.transport);
  const paperMm = usePrinterStore((s) => s.paperMm);
  const openDrawerOnCash = usePrinterStore((s) => s.openDrawerOnCash);

  return useCallback(
    async (receipt: Receipt, options: { copy?: boolean } = {}) => {
      const paidInCash = receipt.order.payments.some((p) => p.method === "cash");

      if (transport) {
        try {
          const bytes = buildReceiptBytes(receipt, String(paperMm) as "58" | "80", {
            openDrawer: openDrawerOnCash && paidInCash,
            copy: options.copy,
          });
          await transport.write(bytes);
          return;
        } catch (error) {
          toast.error(
            `${transport.label} did not respond. Falling back to the print dialog.`,
          );
          console.error("Direct print failed", error);
        }
      }

      printReceiptPdf(receipt, paperMm, options);
    },
    [transport, paperMm, openDrawerOnCash],
  );
}
