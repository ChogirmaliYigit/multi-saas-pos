"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Loader2, Plus, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { FadeIn } from "@/components/motion/fade-in";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { platformApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import type { Plan } from "@/lib/api/platform-types";
import { formatMoney } from "@/lib/format";

export default function PlansPage() {
  const [editing, setEditing] = useState<Plan | null>(null);
  const [creating, setCreating] = useState(false);

  const plans = useQuery({
    queryKey: ["platform", "plans"],
    queryFn: platformApi.plans,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Plans"
        description="Pricing tiers and the limits they enforce."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" /> New plan
          </Button>
        }
      />

      {plans.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-72 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(plans.data ?? []).map((plan, index) => (
            <FadeIn key={plan.id} delay={index * 0.05}>
              <PlanCard plan={plan} onEdit={() => setEditing(plan)} />
            </FadeIn>
          ))}
        </div>
      )}

      <PlanDialog
        plan={editing ?? undefined}
        open={editing !== null || creating}
        onOpenChange={(open) => {
          if (!open) {
            setEditing(null);
            setCreating(false);
          }
        }}
      />
    </div>
  );
}

function PlanCard({ plan, onEdit }: { plan: Plan; onEdit: () => void }) {
  const queryClient = useQueryClient();

  const retire = useMutation({
    mutationFn: () => platformApi.retirePlan(plan.id),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["platform"] });
      toast.success(result.message);
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not retire the plan."),
  });

  const limit = (value: number | null) => value ?? "Unlimited";

  return (
    <Card className={plan.is_active ? "" : "border-dashed opacity-70"}>
      <CardHeader>
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2">
            {plan.name}
            {!plan.is_active && (
              <Badge variant="outline" className="gap-1">
                <Archive className="size-3" /> Retired
              </Badge>
            )}
          </CardTitle>
          <CardDescription>{plan.description ?? plan.code}</CardDescription>
        </div>

        <div className="flex items-baseline gap-1 pt-2">
          <span className="numeric text-3xl font-semibold">
            {formatMoney(plan.price_monthly, plan.currency)}
          </span>
          <span className="text-muted-foreground text-sm">/month</span>
        </div>
        <p className="text-muted-foreground text-xs">
          {formatMoney(plan.price_yearly, plan.currency)}/year · {plan.trial_days}
          -day trial
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        <dl className="space-y-1.5 text-sm">
          <Limit label="Branches" value={limit(plan.max_branches)} />
          <Limit label="Staff accounts" value={limit(plan.max_users)} />
          <Limit label="Products" value={limit(plan.max_products)} />
          <Limit label="Orders / month" value={limit(plan.max_orders_per_month)} />
        </dl>

        <Separator />

        <div className="flex items-center gap-2 text-sm">
          <Users className="text-muted-foreground size-4" />
          <span className="text-muted-foreground">
            {plan.subscriber_count} {plan.subscriber_count === 1 ? "shop" : "shops"}
          </span>
          <span className="numeric ml-auto font-medium">
            {formatMoney(plan.mrr, plan.currency)} MRR
          </span>
        </div>

        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="flex-1" onClick={onEdit}>
            Edit
          </Button>
          {plan.is_active && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => retire.mutate()}
              disabled={retire.isPending}
            >
              {retire.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Archive className="size-4" />
              )}
              Retire
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function Limit({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="numeric">{value}</dd>
    </div>
  );
}

function PlanDialog({
  plan,
  open,
  onOpenChange,
}: {
  plan?: Plan;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-lg">
        <PlanForm
          key={plan?.id ?? "new"}
          plan={plan}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function PlanForm({ plan, onDone }: { plan?: Plan; onDone: () => void }) {
  const queryClient = useQueryClient();
  const isEdit = Boolean(plan);
  const [form, setForm] = useState({
    code: plan?.code ?? "",
    name: plan?.name ?? "",
    description: plan?.description ?? "",
    price_monthly: plan?.price_monthly ?? "0.00",
    price_yearly: plan?.price_yearly ?? "0.00",
    trial_days: String(plan?.trial_days ?? 14),
    max_branches: plan?.max_branches?.toString() ?? "",
    max_users: plan?.max_users?.toString() ?? "",
    max_products: plan?.max_products?.toString() ?? "",
    max_orders_per_month: plan?.max_orders_per_month?.toString() ?? "",
  });

  const numberOrNull = (value: string) =>
    value.trim() === "" ? null : Number.parseInt(value, 10);

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        price_monthly: form.price_monthly || "0",
        price_yearly: form.price_yearly || "0",
        trial_days: Number.parseInt(form.trial_days, 10) || 0,
        max_branches: numberOrNull(form.max_branches),
        max_users: numberOrNull(form.max_users),
        max_products: numberOrNull(form.max_products),
        max_orders_per_month: numberOrNull(form.max_orders_per_month),
      };
      if (!isEdit) body.code = form.code.trim().toLowerCase();
      return isEdit
        ? platformApi.updatePlan(plan!.id, body)
        : platformApi.createPlan(body);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["platform"] });
      toast.success(isEdit ? "Plan updated." : "Plan created.");
      onDone();
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not save the plan."),
  });

  const set = (key: keyof typeof form, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <>
      <DialogHeader>
        <DialogTitle>{isEdit ? `Edit ${plan!.name}` : "New plan"}</DialogTitle>
        <DialogDescription>
          {isEdit
            ? `${plan!.subscriber_count} ${plan!.subscriber_count === 1 ? "shop is" : "shops are"} on this plan. Changing the price does not re-bill them — their amount was frozen at signup.`
            : "Leave a limit blank for unlimited."}
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4 py-1">
        <div className="grid grid-cols-2 gap-3">
          <Field>
            <FieldLabel htmlFor="plan-name">Name</FieldLabel>
            <Input
              id="plan-name"
              value={form.name}
              onChange={(event) => set("name", event.target.value)}
              autoFocus
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="plan-code">Code</FieldLabel>
            <Input
              id="plan-code"
              value={form.code}
              onChange={(event) => set("code", event.target.value)}
              disabled={isEdit}
            />
            <FieldDescription>
              {isEdit ? "Fixed once created." : "Lowercase, used at signup."}
            </FieldDescription>
          </Field>
        </div>

        <Field>
          <FieldLabel htmlFor="plan-desc">Description</FieldLabel>
          <Input
            id="plan-desc"
            value={form.description}
            onChange={(event) => set("description", event.target.value)}
          />
        </Field>

        <div className="grid grid-cols-3 gap-3">
          <Field>
            <FieldLabel htmlFor="price-m">Monthly</FieldLabel>
            <Input
              id="price-m"
              inputMode="decimal"
              className="numeric"
              value={form.price_monthly}
              onChange={(event) => set("price_monthly", event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="price-y">Yearly</FieldLabel>
            <Input
              id="price-y"
              inputMode="decimal"
              className="numeric"
              value={form.price_yearly}
              onChange={(event) => set("price_yearly", event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="trial">Trial days</FieldLabel>
            <Input
              id="trial"
              inputMode="numeric"
              className="numeric"
              value={form.trial_days}
              onChange={(event) => set("trial_days", event.target.value)}
            />
          </Field>
        </div>

        <Separator />

        <div className="grid grid-cols-2 gap-3">
          <Field>
            <FieldLabel htmlFor="max-branches">Branches</FieldLabel>
            <Input
              id="max-branches"
              inputMode="numeric"
              className="numeric"
              placeholder="Unlimited"
              value={form.max_branches}
              onChange={(event) => set("max_branches", event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="max-users">Staff accounts</FieldLabel>
            <Input
              id="max-users"
              inputMode="numeric"
              className="numeric"
              placeholder="Unlimited"
              value={form.max_users}
              onChange={(event) => set("max_users", event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="max-products">Products</FieldLabel>
            <Input
              id="max-products"
              inputMode="numeric"
              className="numeric"
              placeholder="Unlimited"
              value={form.max_products}
              onChange={(event) => set("max_products", event.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="max-orders">Orders / month</FieldLabel>
            <Input
              id="max-orders"
              inputMode="numeric"
              className="numeric"
              placeholder="Unlimited"
              value={form.max_orders_per_month}
              onChange={(event) => set("max_orders_per_month", event.target.value)}
            />
          </Field>
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button
          onClick={() => save.mutate()}
          disabled={
            !form.name.trim() || (!isEdit && !form.code.trim()) || save.isPending
          }
        >
          {save.isPending && <Loader2 className="size-4 animate-spin" />}
          {isEdit ? "Save changes" : "Create plan"}
        </Button>
      </DialogFooter>
    </>
  );
}
