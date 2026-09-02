"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { StockLevel } from "@/lib/api/admin-types";
import { inventoryApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";

const MOVEMENT_TYPES = [
  { value: "purchase", label: "Delivery received" },
  { value: "return", label: "Customer return" },
  { value: "waste", label: "Waste / damage" },
  { value: "adjustment", label: "Correction" },
] as const;

export function StockAdjustDialog({
  item,
  open,
  onOpenChange,
}: {
  item: StockLevel | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {item && (
          <StockAdjustForm
            key={item.product_id}
            item={item}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function StockAdjustForm({
  item,
  onDone,
}: {
  item: StockLevel;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  // Two genuinely different operations, not one form with a sign toggle:
  // a delivery is a delta, a stocktake is an absolute figure.
  const [mode, setMode] = useState<"adjust" | "count">("adjust");
  const [movementType, setMovementType] = useState<string>("purchase");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");

  const onHand = Number.parseFloat(item.quantity);
  const entered = Number.parseFloat(amount) || 0;

  // A delivery adds; waste removes. The sign is derived from the reason, so
  // nobody has to remember to type a minus.
  const signedDelta =
    mode === "adjust"
      ? movementType === "waste"
        ? -Math.abs(entered)
        : movementType === "adjustment"
          ? entered
          : Math.abs(entered)
      : entered - onHand;

  const resulting = mode === "adjust" ? onHand + signedDelta : entered;

  const submit = useMutation({
    mutationFn: async () =>
      mode === "adjust"
        ? inventoryApi.adjust({
            product_id: item.product_id,
            quantity: String(signedDelta),
            movement_type: movementType,
            note: note || null,
          })
        : inventoryApi.count({
            product_id: item.product_id,
            counted_quantity: amount,
            note: note || null,
          }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["inventory"] });
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      await queryClient.invalidateQueries({ queryKey: ["analytics"] });
      toast.success(
        mode === "count"
          ? `Counted. Difference recorded: ${signedDelta > 0 ? "+" : ""}${signedDelta}`
          : "Stock updated.",
      );
      onDone();
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not update stock."),
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle>{item.product_name}</DialogTitle>
        <DialogDescription>
          {item.sku} · {item.branch_name} ·{" "}
          <span className="numeric">{onHand}</span> on hand
        </DialogDescription>
      </DialogHeader>

      <Tabs
        value={mode}
        onValueChange={(value) => setMode(value as "adjust" | "count")}
      >
        <TabsList className="w-full">
          <TabsTrigger value="adjust" className="flex-1">
            Adjust
          </TabsTrigger>
          <TabsTrigger value="count" className="flex-1">
            Stocktake
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="space-y-4 py-1">
        {mode === "adjust" && (
          <Field>
            <FieldLabel>Reason</FieldLabel>
            <Select value={movementType} onValueChange={setMovementType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MOVEMENT_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        )}

        <Field>
          <FieldLabel htmlFor="amount">
            {mode === "adjust" ? "Quantity" : "Counted quantity"}
          </FieldLabel>
          <Input
            id="amount"
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            className="numeric h-14 text-center text-2xl"
            autoFocus
          />
          <FieldDescription>
            {mode === "count"
              ? "Enter what is physically on the shelf. The difference is recorded as the shrinkage figure."
              : movementType === "waste"
                ? "Removed from stock."
                : movementType === "adjustment"
                  ? "Signed: use a minus to reduce."
                  : "Added to stock."}
          </FieldDescription>
        </Field>

        <Field>
          <FieldLabel htmlFor="note">Note</FieldLabel>
          <Input
            id="note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Optional"
          />
        </Field>

        {amount !== "" && (
          <div className="bg-muted flex items-center justify-between rounded-lg p-3 text-sm">
            <span className="text-muted-foreground">After this change</span>
            <span className="numeric text-lg font-semibold">
              {resulting}
              {mode === "count" && signedDelta !== 0 && (
                <span className="text-muted-foreground ml-2 text-sm font-normal">
                  ({signedDelta > 0 ? "+" : ""}
                  {signedDelta.toFixed(3).replace(/\.?0+$/, "")})
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button
          onClick={() => submit.mutate()}
          disabled={amount === "" || submit.isPending}
        >
          {submit.isPending && <Loader2 className="size-4 animate-spin" />}
          {mode === "count" ? "Record count" : "Apply"}
        </Button>
      </DialogFooter>
    </>
  );
}
