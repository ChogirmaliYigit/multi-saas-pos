"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { ordersApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

export function RefundDialog({
  orderId,
  open,
  onOpenChange,
}: {
  orderId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-lg">
        {orderId && (
          <RefundForm
            key={orderId}
            orderId={orderId}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function RefundForm({ orderId, onDone }: { orderId: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(true);
  // Generated once per dialog, so a retried request cannot pay out twice.
  const [idempotencyKey] = useState(
    () => globalThis.crypto?.randomUUID?.() ?? String(Date.now()),
  );

  const view = useQuery({
    queryKey: ["orders", orderId, "refundable"],
    queryFn: () => ordersApi.refundable(orderId),
  });

  const currency = view.data?.currency ?? "USD";
  const lines = useMemo(
    () => (view.data?.lines ?? []).filter((l) => Number(l.refundable_quantity) > 0),
    [view.data],
  );

  // Preview only. The server recomputes the amount from the order's own lines
  // and its answer is the one that counts.
  const previewTotal = lines.reduce((sum, line) => {
    const qty = quantities[line.order_item_id] ?? 0;
    const per = Number(line.refundable_amount) / Number(line.refundable_quantity);
    return sum + per * qty;
  }, 0);
  const selectedCount = Object.values(quantities).reduce((a, b) => a + b, 0);

  const submit = useMutation({
    mutationFn: () =>
      ordersApi.refund(orderId, {
        lines: Object.entries(quantities)
          .filter(([, q]) => q > 0)
          .map(([order_item_id, q]) => ({
            order_item_id,
            quantity: String(q),
          })),
        reason: reason.trim() || null,
        restock,
        idempotency_key: idempotencyKey,
      }),
    onSuccess: async (refund) => {
      await queryClient.invalidateQueries({ queryKey: ["orders"] });
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      await queryClient.invalidateQueries({ queryKey: ["analytics"] });
      await queryClient.invalidateQueries({ queryKey: ["shift"] });
      toast.success(
        `${formatMoney(refund.amount, currency)} refunded${refund.restocked ? " and restocked" : ""}.`,
      );
      onDone();
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Refund failed."),
  });

  if (view.isPending) {
    return (
      <div className="space-y-4 py-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  const setQty = (id: string, value: number, max: number) =>
    setQuantities((current) => ({
      ...current,
      [id]: Math.max(0, Math.min(value, max)),
    }));

  const selectAll = () =>
    setQuantities(
      Object.fromEntries(
        lines.map((l) => [l.order_item_id, Number(l.refundable_quantity)]),
      ),
    );

  return (
    <>
      <DialogHeader>
        <DialogTitle>Refund {view.data?.order_number}</DialogTitle>
        <DialogDescription>
          {formatMoney(view.data?.refundable_total ?? 0, currency)} of{" "}
          {formatMoney(view.data?.total ?? 0, currency)} still refundable
          {Number(view.data?.refunded_total ?? 0) > 0 &&
            ` · ${formatMoney(view.data!.refunded_total, currency)} already returned`}
          .
        </DialogDescription>
      </DialogHeader>

      {lines.length === 0 ? (
        <p className="text-muted-foreground py-8 text-center text-sm">
          Nothing left to refund on this order.
        </p>
      ) : (
        <div className="space-y-4 py-1">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground text-sm">
              Choose what is coming back
            </span>
            <Button variant="ghost" size="sm" onClick={selectAll}>
              Select everything
            </Button>
          </div>

          <ul className="divide-y rounded-lg border">
            {lines.map((line) => {
              const max = Number(line.refundable_quantity);
              const qty = quantities[line.order_item_id] ?? 0;
              return (
                <li
                  key={line.order_item_id}
                  className={cn(
                    "flex items-center gap-3 p-3",
                    qty > 0 && "bg-accent/40",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {line.product_name}
                    </p>
                    <p className="numeric text-muted-foreground text-xs">
                      {formatMoney(line.unit_price, currency)} · {max} available
                      {Number(line.refunded_quantity) > 0 &&
                        ` · ${line.refunded_quantity} already returned`}
                    </p>
                  </div>
                  <Input
                    inputMode="numeric"
                    value={qty}
                    onChange={(e) =>
                      setQty(
                        line.order_item_id,
                        Number.parseFloat(e.target.value) || 0,
                        max,
                      )
                    }
                    className="numeric h-9 w-16 text-center"
                  />
                  <span className="numeric w-20 shrink-0 text-right text-sm">
                    {formatMoney(
                      (Number(line.refundable_amount) / max) * qty,
                      currency,
                    )}
                  </span>
                </li>
              );
            })}
          </ul>

          <Field>
            <FieldLabel htmlFor="reason">Reason</FieldLabel>
            <Input
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Faulty, changed mind, wrong size…"
            />
          </Field>

          <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
            <div className="space-y-0.5">
              <FieldLabel htmlFor="restock">Put stock back</FieldLabel>
              <FieldDescription>
                Turn off for damaged goods — the customer is still paid, the item is
                not returned to the shelf.
              </FieldDescription>
            </div>
            <Switch id="restock" checked={restock} onCheckedChange={setRestock} />
          </div>

          <div className="bg-muted flex items-baseline justify-between rounded-lg p-3">
            <span className="text-sm font-medium">Refund total</span>
            <span className="numeric text-2xl font-semibold">
              {formatMoney(previewTotal, currency)}
            </span>
          </div>
        </div>
      )}

      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button
          variant="destructive"
          onClick={() => submit.mutate()}
          disabled={selectedCount === 0 || submit.isPending}
        >
          {submit.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RotateCcw className="size-4" />
          )}
          Refund {formatMoney(previewTotal, currency)}
        </Button>
      </DialogFooter>
    </>
  );
}
