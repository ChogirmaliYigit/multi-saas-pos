"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Minus, Plus, ShoppingCart, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  type CartLine,
  formatQuantity,
  lineTotalCents,
  useCartStore,
} from "@/lib/stores/cart-store";
import { formatCents } from "@/lib/pos/money";
import { cn } from "@/lib/utils";

export function CartPanel({
  currency,
  totals,
  onCheckout,
  checkoutDisabled,
}: {
  currency: string;
  totals: {
    subtotal: number;
    discountTotal: number;
    taxTotal: number;
    total: number;
    itemCount: number;
  };
  onCheckout: () => void;
  checkoutDisabled: boolean;
}) {
  const lines = useCartStore((s) => s.lines);
  const selectedKey = useCartStore((s) => s.selectedKey);
  const select = useCartStore((s) => s.select);
  const adjustQuantity = useCartStore((s) => s.adjustQuantity);
  const removeLine = useCartStore((s) => s.removeLine);
  const clear = useCartStore((s) => s.clear);
  const hasInclusiveTax = lines.some((line) => line.taxInclusive);

  return (
    <aside className="bg-background flex w-full flex-col border-l md:w-[380px] lg:w-[420px]">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
        <ShoppingCart className="text-muted-foreground size-4.5" />
        <span className="font-medium">Cart</span>
        {lines.length > 0 && (
          <span className="numeric text-muted-foreground text-sm">
            {totals.itemCount} item{totals.itemCount === 1 ? "" : "s"}
          </span>
        )}
        <div className="flex-1" />
        {lines.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={clear}
            className="text-muted-foreground"
          >
            <Trash2 className="size-4" /> Clear
          </Button>
        )}
      </div>

      <ScrollArea className="flex-1">
        {lines.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-6 py-20 text-center">
            <ShoppingCart className="text-muted-foreground/60 size-8" />
            <p className="text-muted-foreground text-sm">
              Scan an item or tap the grid to start.
            </p>
          </div>
        ) : (
          <ul className="divide-y">
            <AnimatePresence initial={false}>
              {lines.map((line) => (
                <CartRow
                  key={line.key}
                  line={line}
                  currency={currency}
                  selected={line.key === selectedKey}
                  onSelect={() => select(line.key)}
                  onAdjust={(delta) => adjustQuantity(line.key, delta)}
                  onRemove={() => removeLine(line.key)}
                />
              ))}
            </AnimatePresence>
          </ul>
        )}
      </ScrollArea>

      <div className="bg-muted/30 shrink-0 border-t p-4">
        <dl className="space-y-1.5 text-sm">
          <Row label="Subtotal" value={formatCents(totals.subtotal, currency)} />
          {totals.discountTotal > 0 && (
            <Row
              label="Discount"
              value={`-${formatCents(totals.discountTotal, currency)}`}
              tone="positive"
            />
          )}
          {totals.taxTotal > 0 && (
            <Row
              label={hasInclusiveTax ? "Tax (incl.)" : "Tax"}
              value={formatCents(totals.taxTotal, currency)}
            />
          )}
        </dl>

        <Separator className="my-3" />

        <div className="flex items-baseline justify-between">
          <span className="text-sm font-medium">Total</span>
          {/*
            The total is the one number the cashier and the customer both look
            at, so it is the largest thing on the panel. `numeric` keeps the
            digits from shifting sideways as it changes.
          */}
          <motion.span
            key={totals.total}
            initial={{ scale: 0.96, opacity: 0.7 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.15 }}
            className="numeric text-3xl font-semibold"
          >
            {formatCents(totals.total, currency)}
          </motion.span>
        </div>

        <Button
          size="lg"
          className="mt-4 h-14 w-full text-base"
          onClick={onCheckout}
          disabled={checkoutDisabled || lines.length === 0}
        >
          Charge {formatCents(totals.total, currency)}
        </Button>
      </div>
    </aside>
  );
}

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "positive";
}) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn("numeric", tone === "positive" && "text-primary")}>
        {value}
      </dd>
    </div>
  );
}

function CartRow({
  line,
  currency,
  selected,
  onSelect,
  onAdjust,
  onRemove,
}: {
  line: CartLine;
  currency: string;
  selected: boolean;
  onSelect: () => void;
  onAdjust: (deltaMilli: number) => void;
  onRemove: () => void;
}) {
  // Weighed goods step by 100g; countable goods by 1.
  const step = line.unit === "kg" || line.unit === "liter" ? 100 : 1000;
  const overStock =
    line.stockAvailable !== null && line.quantityMilli / 1000 > line.stockAvailable;

  return (
    <motion.li
      layout
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.16 }}
      onClick={onSelect}
      className={cn(
        "pos-surface flex flex-col gap-2 px-4 py-3",
        selected && "bg-accent/50",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{line.name}</p>
          <p className="numeric text-muted-foreground text-xs">
            {formatCents(line.unitPriceCents, currency)} · {line.sku}
          </p>
        </div>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onRemove();
          }}
          aria-label={`Remove ${line.name}`}
          className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive rounded p-1"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="size-9"
            onClick={(event) => {
              event.stopPropagation();
              onAdjust(-step);
            }}
            aria-label="Decrease quantity"
          >
            <Minus className="size-4" />
          </Button>
          <span className="numeric w-16 text-center text-sm font-medium">
            {formatQuantity(line)}
            {line.unit !== "piece" && (
              <span className="text-muted-foreground ml-0.5 text-xs">
                {line.unit === "kg" ? "kg" : ""}
              </span>
            )}
          </span>
          <Button
            variant="outline"
            size="icon"
            className="size-9"
            onClick={(event) => {
              event.stopPropagation();
              onAdjust(step);
            }}
            aria-label="Increase quantity"
          >
            <Plus className="size-4" />
          </Button>
        </div>

        <span className="numeric text-sm font-semibold">
          {formatCents(lineTotalCents(line), currency)}
        </span>
      </div>

      {overStock && (
        // Warn, do not block: shops sell past a wrong stock count all the
        // time, and the server is the one that enforces it.
        <p className="text-destructive text-xs">
          Only {line.stockAvailable} in stock
        </p>
      )}
    </motion.li>
  );
}
