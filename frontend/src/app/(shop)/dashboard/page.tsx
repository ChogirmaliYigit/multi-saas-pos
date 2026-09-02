"use client";

import { useQuery } from "@tanstack/react-query";
import { Boxes, Receipt, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import { useState } from "react";

import { LowStockList } from "@/components/admin/low-stock-list";
import { HourlyChart } from "@/components/charts/hourly-chart";
import { PaymentSplit } from "@/components/charts/payment-split";
import { RevenueChart } from "@/components/charts/revenue-chart";
import { TopProductsChart } from "@/components/charts/top-products-chart";
import { PageHeader } from "@/components/layout/page-header";
import { FadeIn } from "@/components/motion/fade-in";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { analyticsApi } from "@/lib/api/endpoints";
import { formatMoney } from "@/lib/format";
import { useAuthStore } from "@/lib/stores/auth-store";
import { cn } from "@/lib/utils";

const RANGES = [7, 30, 90] as const;

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const [days, setDays] = useState<(typeof RANGES)[number]>(30);

  const summary = useQuery({
    queryKey: ["analytics", "dashboard"],
    queryFn: () => analyticsApi.dashboard(),
  });
  const revenue = useQuery({
    queryKey: ["analytics", "revenue", days],
    queryFn: () => analyticsApi.revenue(days),
  });
  const topProducts = useQuery({
    queryKey: ["analytics", "top-products", days],
    queryFn: () => analyticsApi.topProducts(days),
  });
  const lowStock = useQuery({
    queryKey: ["analytics", "low-stock"],
    queryFn: () => analyticsApi.lowStock(8),
  });
  const payments = useQuery({
    queryKey: ["analytics", "payments", days],
    queryFn: () => analyticsApi.payments(days),
  });
  const hourly = useQuery({
    queryKey: ["analytics", "hourly"],
    queryFn: () => analyticsApi.hourly(7),
  });

  const currency = summary.data?.currency ?? "USD";
  const firstName = user?.full_name.split(" ")[0] ?? "there";

  const today = Number.parseFloat(summary.data?.revenue_today ?? "0");
  const yesterday = Number.parseFloat(summary.data?.revenue_yesterday ?? "0");
  const change = yesterday > 0 ? ((today - yesterday) / yesterday) * 100 : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Good to see you, ${firstName}`}
        description="Today's trading at a glance."
        actions={
          <div className="flex items-center gap-1 rounded-lg border p-0.5">
            {/* One filter row above the charts, not per-card controls. */}
            {RANGES.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setDays(option)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm transition-colors",
                  days === option
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {option}d
              </button>
            ))}
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Revenue today"
          value={formatMoney(today, currency)}
          hint={
            change === null
              ? "No trading yesterday"
              : `${change >= 0 ? "+" : ""}${change.toFixed(0)}% vs yesterday`
          }
          trend={change === null ? undefined : change >= 0 ? "up" : "down"}
          loading={summary.isPending}
          delay={0}
        />
        <StatTile
          label="Orders today"
          value={String(summary.data?.orders_today ?? 0)}
          hint={`Average basket ${formatMoney(summary.data?.average_basket ?? 0, currency)}`}
          icon={Receipt}
          loading={summary.isPending}
          delay={0.05}
        />
        <StatTile
          label="Gross margin today"
          value={formatMoney(summary.data?.gross_margin_today ?? 0, currency)}
          hint={`${formatMoney(summary.data?.revenue_month ?? 0, currency)} this month`}
          icon={Wallet}
          loading={summary.isPending}
          delay={0.1}
        />
        <StatTile
          label="Needs restocking"
          value={String(
            (summary.data?.low_stock_count ?? 0) +
              (summary.data?.out_of_stock_count ?? 0),
          )}
          hint={`${summary.data?.out_of_stock_count ?? 0} out of stock`}
          icon={Boxes}
          loading={summary.isPending}
          delay={0.15}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <FadeIn delay={0.2} className="lg:col-span-2">
          <Card className="h-full">
            <CardHeader>
              <CardTitle>Revenue</CardTitle>
              <CardDescription>
                Daily takings over the last {days} days
              </CardDescription>
            </CardHeader>
            <CardContent>
              {revenue.isPending ? (
                <Skeleton className="h-[260px] w-full" />
              ) : (
                <RevenueChart data={revenue.data ?? []} currency={currency} />
              )}
            </CardContent>
          </Card>
        </FadeIn>

        <FadeIn delay={0.25}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>How customers paid</CardTitle>
              <CardDescription>Last {days} days</CardDescription>
            </CardHeader>
            <CardContent>
              {payments.isPending ? (
                <Skeleton className="h-[180px] w-full" />
              ) : (
                <PaymentSplit data={payments.data ?? []} currency={currency} />
              )}
            </CardContent>
          </Card>
        </FadeIn>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <FadeIn delay={0.3}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>Best sellers</CardTitle>
              <CardDescription>By revenue, last {days} days</CardDescription>
            </CardHeader>
            <CardContent>
              {topProducts.isPending ? (
                <Skeleton className="h-[240px] w-full" />
              ) : (topProducts.data ?? []).length === 0 ? (
                <p className="text-muted-foreground py-10 text-center text-sm">
                  No sales in this period yet.
                </p>
              ) : (
                <TopProductsChart
                  data={topProducts.data ?? []}
                  currency={currency}
                />
              )}
            </CardContent>
          </Card>
        </FadeIn>

        <FadeIn delay={0.35}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>Low stock</CardTitle>
              <CardDescription>At or below the reorder level</CardDescription>
            </CardHeader>
            <CardContent>
              {lowStock.isPending ? (
                <Skeleton className="h-[200px] w-full" />
              ) : (
                <LowStockList items={lowStock.data ?? []} />
              )}
            </CardContent>
          </Card>
        </FadeIn>
      </div>

      <FadeIn delay={0.4}>
        <Card>
          <CardHeader>
            <CardTitle>Busiest hours</CardTitle>
            <CardDescription>Revenue by hour of day, last 7 days</CardDescription>
          </CardHeader>
          <CardContent>
            {hourly.isPending ? (
              <Skeleton className="h-[200px] w-full" />
            ) : (
              <HourlyChart data={hourly.data ?? []} currency={currency} />
            )}
          </CardContent>
        </Card>
      </FadeIn>
    </div>
  );
}

function StatTile({
  label,
  value,
  hint,
  icon: Icon,
  trend,
  loading,
  delay,
}: {
  label: string;
  value: string;
  hint: string;
  icon?: typeof Receipt;
  trend?: "up" | "down";
  loading: boolean;
  delay: number;
}) {
  const TrendIcon = trend === "up" ? TrendingUp : TrendingDown;

  return (
    <FadeIn delay={delay}>
      <Card className="gap-0">
        <CardContent className="flex items-start justify-between gap-4 p-5">
          <div className="min-w-0 space-y-1">
            <p className="text-muted-foreground truncate text-sm">{label}</p>
            {loading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              /* A hero number: the largest thing on the tile, tabular so it
                 does not jitter as it updates. */
              <p className="numeric text-2xl font-semibold">{value}</p>
            )}
            <p className="text-muted-foreground flex items-center gap-1 truncate text-xs">
              {trend && <TrendIcon className="size-3 shrink-0" />}
              {hint}
            </p>
          </div>
          {Icon && (
            <span className="bg-muted text-muted-foreground flex size-9 shrink-0 items-center justify-center rounded-lg">
              <Icon className="size-4.5" />
            </span>
          )}
        </CardContent>
      </Card>
    </FadeIn>
  );
}
