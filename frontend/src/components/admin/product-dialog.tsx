"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import type { ProductDetail } from "@/lib/api/admin-types";
import { catalogApi, productsApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";

const UNITS = ["piece", "kg", "gram", "liter", "meter", "pack", "box"] as const;

interface FormState {
  name: string;
  sku: string;
  barcode: string;
  price: string;
  cost_price: string;
  category_id: string;
  tax_rate_id: string;
  unit: string;
  low_stock_threshold: string;
  opening_stock: string;
  track_stock: boolean;
  is_favorite: boolean;
}

function initial(product?: ProductDetail): FormState {
  return {
    name: product?.name ?? "",
    sku: product?.sku ?? "",
    barcode: product?.barcode ?? "",
    price: product?.price ?? "",
    cost_price: product?.cost_price ?? "0.00",
    category_id: product?.category_id ?? "",
    tax_rate_id: product?.tax_rate_id ?? "",
    unit: product?.unit ?? "piece",
    low_stock_threshold: product?.low_stock_threshold ?? "0",
    opening_stock: "",
    track_stock: product?.track_stock ?? true,
    is_favorite: product?.is_favorite ?? false,
  };
}

export function ProductDialog({
  productId,
  open,
  onOpenChange,
}: {
  /** null means "new product". */
  productId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  // Fetch the full record. The catalog list row omits description and
  // tax_rate_id, and a form seeded from it would submit them as null on save
  // -- silently stripping a product's tax rate the first time anyone edits it.
  const detail = useQuery({
    queryKey: ["catalog", "product", productId],
    queryFn: () => productsApi.get(productId!),
    enabled: open && productId !== null,
  });

  const loading = productId !== null && detail.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-lg">
        {loading ? (
          <div className="space-y-4 py-4">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : (
          /* Keyed so switching rows resets the form rather than carrying the
             previous product's values across. */
          <ProductForm
            key={productId ?? "new"}
            product={detail.data}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ProductForm({
  product,
  onDone,
}: {
  product?: ProductDetail;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(() => initial(product));
  const isEdit = Boolean(product);

  const categories = useQuery({
    queryKey: ["catalog", "categories"],
    queryFn: catalogApi.categories,
  });
  const taxRates = useQuery({
    queryKey: ["catalog", "tax-rates"],
    queryFn: productsApi.taxRates,
  });

  const save = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        name: form.name.trim(),
        sku: form.sku.trim(),
        barcode: form.barcode.trim() || null,
        price: form.price || "0",
        cost_price: form.cost_price || "0",
        unit: form.unit,
        low_stock_threshold: form.low_stock_threshold || "0",
        track_stock: form.track_stock,
        is_favorite: form.is_favorite,
        category_id: form.category_id || null,
        tax_rate_id: form.tax_rate_id || null,
      };
      if (!isEdit && form.opening_stock) {
        body.opening_stock = form.opening_stock;
      }
      return isEdit
        ? productsApi.update(product!.id, body)
        : productsApi.create(body);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      await queryClient.invalidateQueries({ queryKey: ["inventory"] });
      await queryClient.invalidateQueries({ queryKey: ["analytics"] });
      toast.success(isEdit ? "Product updated." : "Product added.");
      onDone();
    },
    onError: (error) => {
      if (isApiError(error) && error.isBillingBlock) {
        toast.error(error.message, { duration: 8000 });
        return;
      }
      toast.error(
        isApiError(error) ? error.message : "Could not save the product.",
      );
    },
  });

  const priceNumber = Number.parseFloat(form.price) || 0;
  const costNumber = Number.parseFloat(form.cost_price) || 0;
  const margin =
    priceNumber > 0 ? ((priceNumber - costNumber) / priceNumber) * 100 : 0;
  const canSave = form.name.trim() && form.sku.trim() && form.price;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <>
      <DialogHeader>
        <DialogTitle>{isEdit ? "Edit product" : "New product"}</DialogTitle>
        <DialogDescription>
          {isEdit ? product!.sku : "SKU and barcode must be unique in your shop."}
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4 py-2">
        <Field>
          <FieldLabel htmlFor="name">Name</FieldLabel>
          <Input
            id="name"
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
            autoFocus
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field>
            <FieldLabel htmlFor="sku">SKU</FieldLabel>
            <Input
              id="sku"
              value={form.sku}
              onChange={(e) => set("sku", e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="barcode">Barcode</FieldLabel>
            <Input
              id="barcode"
              inputMode="numeric"
              value={form.barcode}
              onChange={(e) => set("barcode", e.target.value)}
            />
            <FieldDescription>Scanned at the till.</FieldDescription>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field>
            <FieldLabel htmlFor="price">Sell price</FieldLabel>
            <Input
              id="price"
              inputMode="decimal"
              value={form.price}
              onChange={(e) => set("price", e.target.value)}
              className="numeric"
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="cost">Cost price</FieldLabel>
            <Input
              id="cost"
              inputMode="decimal"
              value={form.cost_price}
              onChange={(e) => set("cost_price", e.target.value)}
              className="numeric"
            />
            <FieldDescription>
              {/* Live margin: the number an owner actually prices against. */}
              Margin {margin.toFixed(0)}%
            </FieldDescription>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field>
            <FieldLabel>Category</FieldLabel>
            <Select
              value={form.category_id || "none"}
              onValueChange={(value) =>
                set("category_id", value === "none" ? "" : value)
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Uncategorised" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Uncategorised</SelectItem>
                {(categories.data ?? []).map((category) => (
                  <SelectItem key={category.id} value={category.id}>
                    {category.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel>Tax rate</FieldLabel>
            <Select
              value={form.tax_rate_id || "none"}
              onValueChange={(value) =>
                set("tax_rate_id", value === "none" ? "" : value)
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="No tax" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No tax</SelectItem>
                {(taxRates.data ?? []).map((rate) => (
                  <SelectItem key={rate.id} value={rate.id}>
                    {rate.name} {rate.is_inclusive ? "(incl.)" : "(excl.)"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field>
            <FieldLabel>Unit</FieldLabel>
            <Select value={form.unit} onValueChange={(value) => set("unit", value)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {UNITS.map((unit) => (
                  <SelectItem key={unit} value={unit}>
                    {unit}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="threshold">Reorder level</FieldLabel>
            <Input
              id="threshold"
              inputMode="decimal"
              value={form.low_stock_threshold}
              onChange={(e) => set("low_stock_threshold", e.target.value)}
              className="numeric"
            />
          </Field>
        </div>

        {!isEdit && (
          <Field>
            <FieldLabel htmlFor="opening">Opening stock</FieldLabel>
            <Input
              id="opening"
              inputMode="decimal"
              value={form.opening_stock}
              onChange={(e) => set("opening_stock", e.target.value)}
              className="numeric"
            />
            <FieldDescription>
              Recorded as a stock movement, so day-one quantity is auditable.
            </FieldDescription>
          </Field>
        )}

        <div className="flex items-center justify-between gap-4 rounded-lg border p-3">
          <div className="space-y-0.5">
            <FieldLabel htmlFor="track">Track stock</FieldLabel>
            <FieldDescription>
              Turn off for services and unlimited items.
            </FieldDescription>
          </div>
          <Switch
            id="track"
            checked={form.track_stock}
            onCheckedChange={(value) => set("track_stock", value)}
          />
        </div>

        <div className="flex items-center justify-between gap-4 rounded-lg border p-3">
          <div className="space-y-0.5">
            <FieldLabel htmlFor="favorite">Pin to POS grid</FieldLabel>
            <FieldDescription>Shows first on the terminal.</FieldDescription>
          </div>
          <Switch
            id="favorite"
            checked={form.is_favorite}
            onCheckedChange={(value) => set("is_favorite", value)}
          />
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button onClick={() => save.mutate()} disabled={!canSave || save.isPending}>
          {save.isPending && <Loader2 className="size-4 animate-spin" />}
          {isEdit ? "Save changes" : "Add product"}
        </Button>
      </DialogFooter>
    </>
  );
}
