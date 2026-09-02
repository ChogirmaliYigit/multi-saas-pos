"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2, CreditCard, Receipt, TrendingUp, Users } from "lucide-react";
import Link from "next/link";

import { MrrChart } from "@/components/charts/mrr-chart";
import { PageHeader } from "@/components/layout/page-header";
import { FadeIn } from "@/components/motion/fade-in";
import { TenantStatusBadge } from "@/components/platform/tenant-status-badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { platformApi } from "@/lib/api/endpoints";
import { formatDate, formatMoney } from "@/lib/format";

export default function PlatformOverviewPage() {
  const metrics = useQuery({
    queryKey: ["platform", "metrics"],
    queryFn: platformApi.metrics,
  });
  const mrr = useQuery({
    queryKey: ["platform", "mrr"],
    queryFn: () => platformApi.mrr(12),
  });
  const recent = useQuery({
    queryKey: ["platform", "tenants", "recent"],
    queryFn: () => platformApi.tenants({ size: 5 }),
  });

  const currency = metrics.data?.currency ?? "USD";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Platform overview"
        description="Every shop on the platform, and what they are worth."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile
          label="MRR"
          value={formatMoney(metrics.data?.mrr ?? 0, currency)}
          hint={`${formatMoney(metrics.data?.arr ?? 0, currency)} ARR`}
          icon={TrendingUp}
          loading={metrics.isPending}
          delay={0}
        />
        <MetricTile
          label="Trial pipeline"
          value={formatMoney(metrics.data?.trial_pipeline_mrr ?? 0, currency)}
          // Trials are pipeline, not revenue. Keeping them out of MRR is the
          // difference between a dashboard and a sales pitch to yourself.
          hint={`${metrics.data?.trialing_tenants ?? 0} shops trialing`}
          icon={CreditCard}
          loading={metrics.isPending}
          delay={0.05}
        />
        <MetricTile
          label="Shops"
          value={String(metrics.data?.total_tenants ?? 0)}
          hint={`${metrics.data?.active_tenants ?? 0} active · ${metrics.data?.suspended_tenants ?? 0} suspended`}
          icon={Building2}
          loading={metrics.isPending}
          delay={0.1}
        />
        <MetricTile
          label="Staff accounts"
          value={String(metrics.data?.total_users ?? 0)}
          hint={`+${metrics.data?.new_tenants_this_month ?? 0} shops this month`}
          icon={Users}
          loading={metrics.isPending}
          delay={0.15}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <FadeIn delay={0.2} className="lg:col-span-2">
          <Card className="h-full">
            <CardHeader>
              <CardTitle>Recurring revenue</CardTitle>
              <CardDescription>
                Last 12 months. Approximated from current subscription amounts —
                exact history needs a subscription-events log.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {mrr.isPending ? (
                <Skeleton className="h-[240px] w-full" />
              ) : (
                <MrrChart data={mrr.data ?? []} currency={currency} />
              )}
            </CardContent>
          </Card>
        </FadeIn>

        <FadeIn delay={0.25}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>Platform activity</CardTitle>
              <CardDescription>Across every shop, last 30 days</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Stat
                label="Orders processed"
                value={(metrics.data?.orders_last_30_days ?? 0).toLocaleString()}
                icon={Receipt}
              />
              <Stat
                label="Gross merchandise value"
                value={formatMoney(metrics.data?.gmv_last_30_days ?? 0, currency)}
                icon={TrendingUp}
              />
              <Stat
                label="Churned this month"
                value={String(metrics.data?.churned_this_month ?? 0)}
                icon={Building2}
              />
            </CardContent>
          </Card>
        </FadeIn>
      </div>

      <FadeIn delay={0.3}>
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div className="space-y-1.5">
              <CardTitle>Newest shops</CardTitle>
              <CardDescription>Most recent signups</CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/platform/tenants">View all</Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {recent.isPending ? (
              <div className="space-y-3 p-6">
                {Array.from({ length: 3 }).map((_, index) => (
                  <Skeleton key={index} className="h-10 w-full" />
                ))}
              </div>
            ) : (recent.data?.items ?? []).length === 0 ? (
              <p className="text-muted-foreground py-12 text-center text-sm">
                No shops yet.
              </p>
            ) : (
              <ul className="divide-y">
                {(recent.data?.items ?? []).map((tenant) => (
                  <li key={tenant.id} className="flex items-center gap-3 px-6 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{tenant.name}</p>
                      <p className="text-muted-foreground truncate text-xs">
                        {tenant.slug} · joined {formatDate(tenant.created_at)}
                      </p>
                    </div>
                    <span className="text-muted-foreground hidden text-sm sm:block">
                      {tenant.plan_name ?? "No plan"}
                    </span>
                    <TenantStatusBadge status={tenant.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </FadeIn>
    </div>
  );
}

function MetricTile({
  label,
  value,
  hint,
  icon: Icon,
  loading,
  delay,
}: {
  label: string;
  value: string;
  hint: string;
  icon: typeof Building2;
  loading: boolean;
  delay: number;
}) {
  return (
    <FadeIn delay={delay}>
      <Card className="gap-0">
        <CardContent className="flex items-start justify-between gap-4 p-5">
          <div className="min-w-0 space-y-1">
            <p className="text-muted-foreground truncate text-sm">{label}</p>
            {loading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <p className="numeric text-2xl font-semibold">{value}</p>
            )}
            <p className="text-muted-foreground truncate text-xs">{hint}</p>
          </div>
          <span className="bg-muted text-muted-foreground flex size-9 shrink-0 items-center justify-center rounded-lg">
            <Icon className="size-4.5" />
          </span>
        </CardContent>
      </Card>
    </FadeIn>
  );
}

function Stat({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof Receipt;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
        <Icon className="size-4" />
      </span>
      <span className="text-muted-foreground min-w-0 flex-1 truncate text-sm">
        {label}
      </span>
      <span className="numeric shrink-0 font-semibold">{value}</span>
    </div>
  );
}
