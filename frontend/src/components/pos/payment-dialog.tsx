"use client";

import { Banknote, CreditCard, Loader2, Smartphone } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import type { PaymentMethod } from "@/lib/api/pos-types";
import { fromCents, formatCents, toCents } from "@/lib/pos/money";
import { cn } from "@/lib/utils";

const METHODS: { value: PaymentMethod; label: string; icon: typeof Banknote }[] = [
  { value: "cash", label: "Cash", icon: Banknote },
  { value: "card", label: "Card", icon: CreditCard },
  { value: "mobile", label: "Mobile", icon: Smartphone },
];

/**
 * Rounded-up cash amounts a customer is likely to hand over. Computed from
 * the total rather than fixed, so a 6.40 sale offers 10 and 20 rather than
 * a generic list the cashier has to ignore.
 */
function quickCashOptions(totalCents: number): number[] {
  const options = new Set<number>([totalCents]);
  for (const step of [500, 1000, 2000, 5000]) {
    options.add(Math.ceil(totalCents / step) * step);
  }
  return [...options].sort((a, b) => a - b).slice(0, 5);
}

interface PaymentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  totalCents: number;
  currency: string;
  isSubmitting: boolean;
  onConfirm: (
    payments: {
      method: PaymentMethod;
      amount: string;
      tendered_amount?: string;
      card_last4?: string;
    }[],
  ) => void;
}

export function PaymentDialog({ open, onOpenChange, ...rest }: PaymentDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {/*
          The form lives in a child so Radix unmounting the content on close
          resets it. Resetting via an effect on `open` would mean a render
          pass where the previous sale's tendered amount is still on screen.
        */}
        <PaymentForm {...rest} />
      </DialogContent>
    </Dialog>
  );
}

function PaymentForm({
  totalCents,
  currency,
  isSubmitting,
  onConfirm,
}: Omit<PaymentDialogProps, "open" | "onOpenChange">) {
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [tendered, setTendered] = useState("");
  const [cardLast4, setCardLast4] = useState("");

  const tenderedCents = tendered ? toCents(tendered) : 0;
  // Card and mobile are settled on the terminal for the exact amount; only
  // cash involves handing over more than the total.
  const effectiveTendered = method === "cash" ? tenderedCents : totalCents;
  const changeCents = Math.max(0, effectiveTendered - totalCents);
  const short = effectiveTendered < totalCents;

  const quickOptions = useMemo(() => quickCashOptions(totalCents), [totalCents]);

  function confirm() {
    if (short) return;
    onConfirm([
      {
        method,
        amount: fromCents(totalCents),
        ...(method === "cash"
          ? { tendered_amount: fromCents(effectiveTendered) }
          : {}),
        ...(method === "card" && cardLast4.length === 4
          ? { card_last4: cardLast4 }
          : {}),
      },
    ]);
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Take payment</DialogTitle>
        <DialogDescription>
          {formatCents(totalCents, currency)} due
        </DialogDescription>
      </DialogHeader>

      <div className="grid grid-cols-3 gap-2">
        {METHODS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => setMethod(option.value)}
            className={cn(
              "touch-target flex flex-col items-center gap-1.5 rounded-lg border p-3 text-sm transition-colors",
              method === option.value
                ? "border-primary bg-primary/10 font-medium"
                : "hover:bg-accent",
            )}
          >
            <option.icon className="size-5" />
            {option.label}
          </button>
        ))}
      </div>

      {method === "cash" ? (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            {quickOptions.map((option) => (
              <Button
                key={option}
                type="button"
                variant="outline"
                className="numeric touch-target"
                onClick={() => setTendered(fromCents(option))}
              >
                {formatCents(option, currency)}
              </Button>
            ))}
          </div>
          <Input
            // inputMode numeric brings up the number pad on a tablet
            // instead of a full keyboard.
            inputMode="decimal"
            placeholder="Amount received"
            value={tendered}
            onChange={(event) => setTendered(event.target.value)}
            className="numeric h-14 text-center text-2xl"
            autoFocus
          />
        </div>
      ) : (
        method === "card" && (
          <Input
            inputMode="numeric"
            maxLength={4}
            placeholder="Card last 4 (optional)"
            value={cardLast4}
            onChange={(event) =>
              setCardLast4(event.target.value.replace(/\D/g, ""))
            }
            className="numeric h-12 text-center"
          />
        )
      )}

      <Separator />

      <div className="space-y-1.5 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Due</span>
          <span className="numeric">{formatCents(totalCents, currency)}</span>
        </div>
        {method === "cash" && (
          <div className="flex items-baseline justify-between">
            <span className="font-medium">Change</span>
            <span
              className={cn(
                "numeric text-2xl font-semibold",
                short && "text-muted-foreground",
              )}
            >
              {formatCents(changeCents, currency)}
            </span>
          </div>
        )}
      </div>

      <Button
        size="lg"
        className="h-14 w-full text-base"
        disabled={short || isSubmitting}
        onClick={confirm}
      >
        {isSubmitting && <Loader2 className="size-4 animate-spin" />}
        {short
          ? `${formatCents(totalCents - effectiveTendered, currency)} short`
          : "Complete sale"}
      </Button>
    </>
  );
}
