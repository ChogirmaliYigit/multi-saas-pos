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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { platformApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import type { TenantSummary } from "@/lib/api/platform-types";
import { formatMoney } from "@/lib/format";

export function ChangePlanDialog({
  tenant,
  open,
  onOpenChange,
}: {
  tenant: TenantSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [planId, setPlanId] = useState("");
  const [cycle, setCycle] = useState<"monthly" | "yearly">("monthly");
  const [activate, setActivate] = useState(false);

  const plans = useQuery({
    queryKey: ["platform", "plans"],
    queryFn: platformApi.plans,
    enabled: open,
  });

  const change = useMutation({
    mutationFn: () =>
      platformApi.changeTenantPlan(tenant!.id, {
        plan_id: planId,
        billing_cycle: cycle,
        activate,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["platform"] });
      toast.success("Plan updated.");
      onOpenChange(false);
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not change the plan."),
  });

  if (!tenant) return null;

  const selected = (plans.data ?? []).find((plan) => plan.id === planId);
  const isTrialing = tenant.subscription_status === "trialing";
  const overUsers =
    selected?.max_users !== null &&
    selected?.max_users !== undefined &&
    tenant.user_count > selected.max_users;
  const overProducts =
    selected?.max_products !== null &&
    selected?.max_products !== undefined &&
    tenant.product_count > selected.max_products;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Change plan</DialogTitle>
          <DialogDescription>
            {tenant.name} is on {tenant.plan_name ?? "no plan"}
            {isTrialing && " (trialing)"}.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">
          <Field>
            <FieldLabel>New plan</FieldLabel>
            <Select value={planId} onValueChange={setPlanId}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a plan" />
              </SelectTrigger>
              <SelectContent>
                {(plans.data ?? []).map((plan) => (
                  <SelectItem key={plan.id} value={plan.id}>
                    {plan.name} — {formatMoney(plan.price_monthly, plan.currency)}
                    /mo{!plan.is_active && " (retired)"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field>
            <FieldLabel>Billing cycle</FieldLabel>
            <Select
              value={cycle}
              onValueChange={(value) => setCycle(value as "monthly" | "yearly")}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="monthly">Monthly</SelectItem>
                <SelectItem value="yearly">Yearly</SelectItem>
              </SelectContent>
            </Select>
            {selected && (
              <FieldDescription>
                {cycle === "monthly"
                  ? `${formatMoney(selected.price_monthly, selected.currency)} per month`
                  : `${formatMoney(selected.price_yearly, selected.currency)} per year`}
              </FieldDescription>
            )}
          </Field>

          {isTrialing && (
            <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
              <div className="space-y-0.5">
                <FieldLabel htmlFor="activate">
                  End the trial and start billing
                </FieldLabel>
                <FieldDescription>
                  Off by default, so correcting a mis-selected tier does not charge
                  them a fortnight early.
                </FieldDescription>
              </div>
              <Switch
                id="activate"
                checked={activate}
                onCheckedChange={setActivate}
              />
            </div>
          )}

          {selected && (
            <div className="bg-muted space-y-2 rounded-lg p-3 text-sm">
              <p className="text-muted-foreground">
                Limits: {selected.max_users ?? "unlimited"} staff ·{" "}
                {selected.max_products ?? "unlimited"} products ·{" "}
                {selected.max_branches ?? "unlimited"} branches
              </p>
              {(overUsers || overProducts) && (
                <p className="text-xs">
                  This shop is already over the new limits. Nothing is deleted —
                  they simply cannot add more until they are back under.
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => change.mutate()}
            disabled={!planId || change.isPending}
          >
            {change.isPending && <Loader2 className="size-4 animate-spin" />}
            Update plan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
