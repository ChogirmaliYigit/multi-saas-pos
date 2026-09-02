"use client";

import { motion } from "framer-motion";
import { Check, Printer, Receipt as ReceiptIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import type { Receipt } from "@/lib/api/pos-types";
import { formatCents, toCents } from "@/lib/pos/money";

/**
 * The change-due screen. On a busy till this is on screen for two seconds, so
 * it shows exactly one number large enough to read at arm's length.
 */
export function SaleCompleteDialog({
  receipt,
  open,
  onOpenChange,
  onPrint,
  onNewSale,
}: {
  receipt: Receipt | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPrint: () => void;
  onNewSale: () => void;
}) {
  if (!receipt) return null;

  const { order } = receipt;
  const changeCents = toCents(order.change_due);
  const currency = order.currency;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm" showCloseButton={false}>
        <DialogTitle className="sr-only">Sale complete</DialogTitle>

        <div className="flex flex-col items-center gap-4 py-2 text-center">
          <motion.span
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 400, damping: 18 }}
            className="bg-primary/15 text-primary flex size-14 items-center justify-center rounded-full"
          >
            <Check className="size-7" strokeWidth={3} />
          </motion.span>

          <div className="space-y-1">
            <p className="text-muted-foreground text-sm">Paid</p>
            <p className="numeric text-2xl font-semibold">
              {formatCents(toCents(order.total), currency)}
            </p>
          </div>

          {changeCents > 0 && (
            <div className="bg-muted w-full rounded-xl p-4">
              <p className="text-muted-foreground text-sm">Change due</p>
              <p className="numeric text-4xl font-bold">
                {formatCents(changeCents, currency)}
              </p>
            </div>
          )}

          <p className="numeric text-muted-foreground text-xs">
            {order.order_number}
          </p>

          <div className="grid w-full grid-cols-2 gap-2 pt-1">
            <Button variant="outline" className="h-12" onClick={onPrint}>
              <Printer className="size-4" /> Print
            </Button>
            <Button className="h-12" onClick={onNewSale} autoFocus>
              <ReceiptIcon className="size-4" /> New sale
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
