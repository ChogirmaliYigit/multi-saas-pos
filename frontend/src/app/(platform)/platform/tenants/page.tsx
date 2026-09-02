"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  CheckCircle2,
  CreditCard,
  MoreHorizontal,
  Search,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { BlockTenantDialog } from "@/components/platform/block-tenant-dialog";
import { ChangePlanDialog } from "@/components/platform/change-plan-dialog";
import { TenantStatusBadge } from "@/components/platform/tenant-status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { platformApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import type { TenantStatus, TenantSummary } from "@/lib/api/platform-types";
import { formatDate, formatMoney } from "@/lib/format";
import { useDebounced } from "@/lib/hooks/use-debounced";
import { cn } from "@/lib/utils";

const FILTERS: { value: TenantStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "trial", label: "Trial" },
  { value: "suspended", label: "Suspended" },
];

export default function TenantsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search, 300);
  const [filter, setFilter] = useState<TenantStatus | "all">("all");
  const [blocking, setBlocking] = useState<TenantSummary | null>(null);
  const [changingPlan, setChangingPlan] = useState<TenantSummary | null>(null);

  const tenants = useQuery({
    queryKey: ["platform", "tenants", debouncedSearch, filter],
    queryFn: () =>
      platformApi.tenants({
        search: debouncedSearch || undefined,
        tenant_status: filter === "all" ? undefined : filter,
        size: 50,
      }),
  });

  const unblock = useMutation({
    mutationFn: (tenant: TenantSummary) =>
      platformApi.setTenantStatus(tenant.id, "active"),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["platform"] });
      toast.success("Shop restored. They can trade again.");
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not restore the shop.",
      ),
  });

  const items = tenants.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Shops"
        description="Every tenant on the platform, what they pay and how they trade."
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative max-w-sm flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search name, address or email"
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-1 rounded-lg border p-0.5">
          {FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setFilter(option.value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm transition-colors",
                filter === option.value
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Shop</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead className="text-right">MRR</TableHead>
                <TableHead className="text-right">Staff</TableHead>
                <TableHead className="text-right">Orders 30d</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {tenants.isPending &&
                Array.from({ length: 5 }).map((_, index) => (
                  <TableRow key={index}>
                    <TableCell colSpan={7}>
                      <Skeleton className="h-8 w-full" />
                    </TableCell>
                  </TableRow>
                ))}

              {!tenants.isPending && items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="text-muted-foreground py-14 text-center"
                  >
                    {search || filter !== "all"
                      ? "No shops match."
                      : "No shops yet."}
                  </TableCell>
                </TableRow>
              )}

              {items.map((tenant) => (
                <TableRow
                  key={tenant.id}
                  className={tenant.status === "suspended" ? "opacity-60" : ""}
                >
                  <TableCell>
                    <span className="block font-medium">{tenant.name}</span>
                    <span className="text-muted-foreground block text-xs">
                      {tenant.slug} · joined {formatDate(tenant.created_at)}
                    </span>
                    {tenant.blocked_reason && (
                      <span className="text-destructive mt-0.5 block text-xs">
                        {tenant.blocked_reason}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <span className="block text-sm">{tenant.plan_name ?? "—"}</span>
                    <span className="text-muted-foreground block text-xs">
                      {tenant.billing_cycle ?? ""}
                    </span>
                  </TableCell>
                  <TableCell className="numeric text-right">
                    {tenant.subscription_status === "trialing" ? (
                      <span className="text-muted-foreground text-xs">
                        in trial
                      </span>
                    ) : (
                      formatMoney(tenant.mrr, tenant.currency)
                    )}
                  </TableCell>
                  <TableCell className="numeric text-muted-foreground text-right">
                    {tenant.user_count}
                  </TableCell>
                  <TableCell className="numeric text-muted-foreground text-right">
                    {tenant.orders_last_30_days}
                  </TableCell>
                  <TableCell>
                    <TenantStatusBadge status={tenant.status} />
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Actions for ${tenant.name}`}
                        >
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setChangingPlan(tenant)}>
                          <CreditCard className="size-4" /> Change plan
                        </DropdownMenuItem>
                        {tenant.status === "suspended" ? (
                          <DropdownMenuItem onClick={() => unblock.mutate(tenant)}>
                            <CheckCircle2 className="size-4" /> Restore access
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem
                            variant="destructive"
                            onClick={() => setBlocking(tenant)}
                          >
                            <Ban className="size-4" /> Suspend
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      <BlockTenantDialog
        tenant={blocking}
        open={blocking !== null}
        onOpenChange={(open) => !open && setBlocking(null)}
      />
      <ChangePlanDialog
        tenant={changingPlan}
        open={changingPlan !== null}
        onOpenChange={(open) => !open && setChangingPlan(null)}
      />
    </div>
  );
}
