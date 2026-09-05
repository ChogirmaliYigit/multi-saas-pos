"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Lock, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { ShopSettings, TaxRate } from "@/lib/api/admin-types";
import { shopApi, taxRatesApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import { Permission } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";

export default function SettingsPage() {
  const canEdit = useAuthStore((s) => s.permissions.has(Permission.TENANT_UPDATE));

  const shop = useQuery({ queryKey: ["shop"], queryFn: () => shopApi.get() });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Shop details, taxes and receipt layout."
      />

      {shop.isPending || !shop.data ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <Tabs defaultValue="shop">
          <TabsList>
            <TabsTrigger value="shop">Shop</TabsTrigger>
            <TabsTrigger value="receipt">Receipt</TabsTrigger>
            <TabsTrigger value="tax">Tax rates</TabsTrigger>
          </TabsList>

          <TabsContent value="shop" className="mt-4">
            <ShopDetails shop={shop.data} canEdit={canEdit} />
          </TabsContent>
          <TabsContent value="receipt" className="mt-4">
            <ReceiptSettings shop={shop.data} canEdit={canEdit} />
          </TabsContent>
          <TabsContent value="tax" className="mt-4">
            <TaxRates canEdit={canEdit} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}

/** Shared save mutation for both settings cards. */
function useSaveShop(successMessage: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => shopApi.update(body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["shop"] });
      // The shell renders the shop name, so refresh the session too.
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      toast.success(successMessage);
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not save."),
  });
}

function ShopDetails({ shop, canEdit }: { shop: ShopSettings; canEdit: boolean }) {
  const save = useSaveShop("Shop details saved.");
  const [form, setForm] = useState({
    name: shop.name,
    legal_name: shop.legal_name ?? "",
    tax_number: shop.tax_number ?? "",
    email: shop.email,
    phone: shop.phone ?? "",
    address: shop.address ?? "",
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Shop details</CardTitle>
        <CardDescription>
          These appear on receipts and on anything you export.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="shop-name">Trading name</FieldLabel>
            <Input
              id="shop-name"
              value={form.name}
              disabled={!canEdit}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="shop-legal">Legal name</FieldLabel>
            <Input
              id="shop-legal"
              value={form.legal_name}
              disabled={!canEdit}
              onChange={(e) => setForm({ ...form, legal_name: e.target.value })}
            />
            <FieldDescription>If different from the trading name.</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="shop-tax">Tax / VAT number</FieldLabel>
            <Input
              id="shop-tax"
              value={form.tax_number}
              disabled={!canEdit}
              onChange={(e) => setForm({ ...form, tax_number: e.target.value })}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="shop-email">Contact email</FieldLabel>
            <Input
              id="shop-email"
              type="email"
              value={form.email}
              disabled={!canEdit}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="shop-phone">Phone</FieldLabel>
            <Input
              id="shop-phone"
              value={form.phone}
              disabled={!canEdit}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="shop-address">Address</FieldLabel>
            <Textarea
              id="shop-address"
              rows={2}
              value={form.address}
              disabled={!canEdit}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
            />
          </Field>
        </div>

        {/* Deliberately read-only. Currency is stamped on every past order and
            the slug is how staff sign in; both are support requests, not
            self-service switches. */}
        <div className="bg-muted/40 grid gap-4 rounded-lg border p-4 sm:grid-cols-3">
          <ReadOnly label="Shop address" value={`${shop.slug}`} />
          <ReadOnly label="Currency" value={shop.currency} />
          <ReadOnly label="Country" value={shop.country_code} />
          <p className="text-muted-foreground col-span-full text-xs">
            <Lock className="mr-1 inline size-3" />
            Changing the currency would re-price every sale already recorded, and
            the address is what staff type to sign in. Contact support to change
            either.
          </p>
        </div>

        {canEdit && (
          <div className="flex justify-end">
            <Button
              onClick={() =>
                save.mutate({
                  name: form.name.trim(),
                  legal_name: form.legal_name.trim() || null,
                  tax_number: form.tax_number.trim() || null,
                  email: form.email.trim(),
                  phone: form.phone.trim() || null,
                  address: form.address.trim() || null,
                })
              }
              disabled={!form.name.trim() || save.isPending}
            >
              {save.isPending && <Loader2 className="size-4 animate-spin" />}
              Save changes
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ReadOnly({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="font-mono text-sm">{value}</p>
    </div>
  );
}

function ReceiptSettings({
  shop,
  canEdit,
}: {
  shop: ShopSettings;
  canEdit: boolean;
}) {
  const save = useSaveShop("Receipt layout saved.");
  const [header, setHeader] = useState(shop.receipt_header ?? "");
  const [footer, setFooter] = useState(shop.receipt_footer ?? "");
  const [width, setWidth] = useState(String(shop.settings?.receipt_width_mm ?? 80));

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Receipt layout</CardTitle>
          <CardDescription>
            Printed above and below the items on every receipt.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field>
            <FieldLabel htmlFor="rcp-header">Header</FieldLabel>
            <Textarea
              id="rcp-header"
              rows={3}
              value={header}
              disabled={!canEdit}
              onChange={(e) => setHeader(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="rcp-footer">Footer</FieldLabel>
            <Textarea
              id="rcp-footer"
              rows={3}
              value={footer}
              disabled={!canEdit}
              onChange={(e) => setFooter(e.target.value)}
            />
            <FieldDescription>
              Returns policy, opening hours, a thank-you.
            </FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="rcp-width">Paper width</FieldLabel>
            <div className="flex gap-2">
              {["58", "80"].map((mm) => (
                <Button
                  key={mm}
                  type="button"
                  variant={width === mm ? "default" : "outline"}
                  disabled={!canEdit}
                  onClick={() => setWidth(mm)}
                >
                  {mm} mm
                </Button>
              ))}
            </div>
            <FieldDescription>
              Match the roll in the printer, or lines wrap mid-word.
            </FieldDescription>
          </Field>

          {canEdit && (
            <div className="flex justify-end">
              <Button
                onClick={() =>
                  save.mutate({
                    receipt_header: header.trim() || null,
                    receipt_footer: footer.trim() || null,
                    settings: { receipt_width_mm: Number(width) },
                  })
                }
                disabled={save.isPending}
              >
                {save.isPending && <Loader2 className="size-4 animate-spin" />}
                Save layout
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preview</CardTitle>
          <CardDescription>Roughly what prints at {width} mm.</CardDescription>
        </CardHeader>
        <CardContent>
          <div
            className="bg-background mx-auto space-y-2 border p-4 font-mono text-xs leading-relaxed"
            style={{ maxWidth: width === "58" ? "22rem" : "28rem" }}
          >
            <p className="text-center font-semibold">{shop.name}</p>
            {shop.address && (
              <p className="text-muted-foreground text-center">{shop.address}</p>
            )}
            {header && <p className="text-center whitespace-pre-line">{header}</p>}
            <p className="text-muted-foreground">------------------------</p>
            <div className="flex justify-between">
              <span>Cola 330ml</span>
              <span className="tabular-nums">1.20</span>
            </div>
            <div className="flex justify-between">
              <span>Bread</span>
              <span className="tabular-nums">2.40</span>
            </div>
            <p className="text-muted-foreground">------------------------</p>
            <div className="flex justify-between font-semibold">
              <span>TOTAL</span>
              <span className="tabular-nums">3.60 {shop.currency}</span>
            </div>
            {footer && (
              <p className="pt-2 text-center whitespace-pre-line">{footer}</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TaxRates({ canEdit }: { canEdit: boolean }) {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [percent, setPercent] = useState("");
  const [inclusive, setInclusive] = useState(true);

  const rates = useQuery({
    queryKey: ["tax-rates"],
    queryFn: () => taxRatesApi.list(),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["tax-rates"] });
    await queryClient.invalidateQueries({ queryKey: ["products"] });
  };

  const create = useMutation({
    mutationFn: () =>
      taxRatesApi.create({
        name: name.trim(),
        // Owners think in percent; the API stores a fraction.
        rate: (Number(percent) / 100).toFixed(4),
        is_inclusive: inclusive,
      }),
    onSuccess: async () => {
      await invalidate();
      setAdding(false);
      setName("");
      setPercent("");
      toast.success("Tax rate added.");
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not add the rate."),
  });

  const setDefault = useMutation({
    mutationFn: (id: string) => taxRatesApi.update(id, { is_default: true }),
    onSuccess: async () => {
      await invalidate();
      toast.success("Default rate updated.");
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not update."),
  });

  const remove = useMutation({
    mutationFn: (id: string) => taxRatesApi.remove(id),
    onSuccess: async (result) => {
      await invalidate();
      toast.success(result.message);
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not remove the rate."),
  });

  const validPercent =
    percent !== "" && Number(percent) >= 0 && Number(percent) <= 100;

  return (
    <Card className="gap-0 overflow-hidden pb-0">
      <CardHeader>
        <CardTitle>Tax rates</CardTitle>
        <CardDescription>
          Editing a rate changes future sales only — every past order kept the rate
          it was rung up at, so last quarter&apos;s return does not move.
        </CardDescription>
      </CardHeader>

      <CardContent className="px-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Rate</TableHead>
                <TableHead>Applied</TableHead>
                <TableHead className="w-32" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rates.isPending && (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Skeleton className="h-8 w-full" />
                  </TableCell>
                </TableRow>
              )}
              {(rates.data ?? []).map((rate: TaxRate) => (
                <TableRow key={rate.id}>
                  <TableCell className="font-medium">
                    {rate.name}
                    {rate.is_default && <Badge className="ml-2">Default</Badge>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {(Number(rate.rate) * 100).toFixed(2)}%
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {rate.is_inclusive ? "Included in price" : "Added at till"}
                  </TableCell>
                  <TableCell>
                    {canEdit && (
                      <div className="flex justify-end gap-1">
                        {!rate.is_default && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDefault.mutate(rate.id)}
                          >
                            Make default
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Remove ${rate.name}`}
                          onClick={() => remove.mutate(rate.id)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {canEdit && (
          <div className="border-t p-4">
            {adding ? (
              <div className="flex flex-wrap items-end gap-3">
                <Field className="w-48">
                  <FieldLabel htmlFor="rate-name">Name</FieldLabel>
                  <Input
                    id="rate-name"
                    value={name}
                    autoFocus
                    onChange={(e) => setName(e.target.value)}
                  />
                </Field>
                <Field className="w-28">
                  <FieldLabel htmlFor="rate-pct">Rate %</FieldLabel>
                  <Input
                    id="rate-pct"
                    inputMode="decimal"
                    value={percent}
                    className="numeric"
                    onChange={(e) => setPercent(e.target.value)}
                  />
                </Field>
                <label className="flex h-9 items-center gap-2 text-sm">
                  <Switch checked={inclusive} onCheckedChange={setInclusive} />
                  Included in price
                </label>
                <div className="ml-auto flex gap-2">
                  <Button variant="outline" onClick={() => setAdding(false)}>
                    Cancel
                  </Button>
                  <Button
                    onClick={() => create.mutate()}
                    disabled={!name.trim() || !validPercent || create.isPending}
                  >
                    {create.isPending && (
                      <Loader2 className="size-4 animate-spin" />
                    )}
                    Add rate
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="outline" onClick={() => setAdding(true)}>
                <Plus className="size-4" /> Add tax rate
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
