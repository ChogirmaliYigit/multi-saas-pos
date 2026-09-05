"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CreditCard,
  ExternalLink,
  Receipt,
} from "lucide-react";

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
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { analyticsApi, billingApi } from "@/lib/api/endpoints";
import { formatDate, formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function BillingPage() {
  const billing = useQuery({
    queryKey: ["billing"],
    queryFn: billingApi.overview,
  });
  const usage = useQuery({
    queryKey: ["analytics", "usage"],
    queryFn: analyticsApi.usage,
  });

  if (billing.isPending) {
    return (
      <div className="space-y-6">
        <PageHeader title="Billing" description="Your plan, invoices and usage." />
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  const data = billing.data!;
  const currency = data.currency;
  const overdue = data.outstanding !== null;
  const suspended = data.tenant_status === "suspended";
  const grace = data.grace_days_remaining;

  return (
    <div className="space-y-6">
      <PageHeader title="Billing" description="Your plan, invoices and usage." />

      {/* The most urgent thing on the page goes first, and only when it
          applies. A permanent banner is one nobody reads. */}
      {overdue && (
        <FadeIn>
          <Card
            className={cn(
              "border-2",
              suspended ? "border-destructive" : "border-amber-500/60",
            )}
          >
            <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
              <AlertTriangle
                className={cn(
                  "size-6 shrink-0",
                  suspended ? "text-destructive" : "text-amber-500",
                )}
              />
              <div className="min-w-0 flex-1">
                <p className="font-medium">
                  {suspended
                    ? "Your shop is suspended"
                    : `Invoice ${data.outstanding!.number} is unpaid`}
                </p>
                <p className="text-muted-foreground text-sm">
                  {suspended
                    ? "Settle the invoice below to start trading again. Your data is untouched."
                    : grace !== null && grace >= 0
                      ? `Pay within ${grace} ${grace === 1 ? "day" : "days"} to keep trading.`
                      : "Pay now to keep trading."}
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                {data.pay_links.length === 0 ? (
                  <span className="text-muted-foreground text-sm">
                    Contact support to pay
                  </span>
                ) : (
                  data.pay_links.map((link) => (
                    <Button key={link.provider} asChild>
                      {/* Leaves our origin, so noopener is not optional. */}
                      <a href={link.url} target="_blank" rel="noopener noreferrer">
                        Pay with {link.label}
                        <ExternalLink className="size-4" />
                      </a>
                    </Button>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </FadeIn>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <FadeIn delay={0.05} className="lg:col-span-2">
          <Card className="h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CreditCard className="size-4.5" />
                {data.plan_name ?? "No plan"}
              </CardTitle>
              <CardDescription>
                {data.status === "trialing"
                  ? data.trial_ends_at
                    ? `Trial ends ${formatDate(data.trial_ends_at)}`
                    : "On trial"
                  : data.current_period_end
                    ? `Renews ${formatDate(data.current_period_end)}`
                    : "No renewal scheduled"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-baseline gap-2">
                <span className="numeric text-3xl font-semibold">
                  {formatMoney(data.amount, currency)}
                </span>
                <span className="text-muted-foreground text-sm">
                  / {data.billing_cycle === "yearly" ? "year" : "month"}
                </span>
                {data.status && (
                  <Badge
                    variant={
                      data.status === "active"
                        ? "default"
                        : data.status === "past_due"
                          ? "destructive"
                          : "secondary"
                    }
                    className="ml-auto"
                  >
                    {data.status.replace("_", " ")}
                  </Badge>
                )}
              </div>

              {usage.data && (
                <>
                  <Separator />
                  <dl className="space-y-3">
                    <UsageRow
                      label="Staff accounts"
                      used={usage.data.users.used}
                      limit={usage.data.users.limit}
                    />
                    <UsageRow
                      label="Products"
                      used={usage.data.products.used}
                      limit={usage.data.products.limit}
                    />
                    <UsageRow
                      label="Branches"
                      used={usage.data.branches.used}
                      limit={usage.data.branches.limit}
                    />
                    <UsageRow
                      label="Orders this month"
                      used={usage.data.orders_this_month.used}
                      limit={usage.data.orders_this_month.limit}
                    />
                  </dl>
                </>
              )}
            </CardContent>
          </Card>
        </FadeIn>

        <FadeIn delay={0.1}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>How to pay</CardTitle>
              <CardDescription>
                Invoices are issued at the end of each period.
              </CardDescription>
            </CardHeader>
            <CardContent className="text-muted-foreground space-y-3 text-sm">
              {data.pay_links.length > 0 ? (
                <>
                  <p>
                    When an invoice is open, a payment button appears at the top of
                    this page.
                  </p>
                  <p>
                    Accepted: {data.pay_links.map((l) => l.label).join(" and ")}.
                  </p>
                </>
              ) : (
                <p>
                  No payment provider is connected yet. Contact support to settle an
                  invoice.
                </p>
              )}
              <p>
                An unpaid invoice suspends trading after a short grace period.
                Nothing is deleted — paying restores access immediately.
              </p>
            </CardContent>
          </Card>
        </FadeIn>
      </div>

      <FadeIn delay={0.15}>
        <Card className="overflow-hidden p-0">
          <CardHeader className="p-6 pb-4">
            <CardTitle>Invoices</CardTitle>
          </CardHeader>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Number</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-32" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.invoices.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-14 text-center">
                      <Receipt className="text-muted-foreground mx-auto mb-2 size-7" />
                      <p className="text-muted-foreground text-sm">
                        No invoices yet.
                      </p>
                    </TableCell>
                  </TableRow>
                )}
                {data.invoices.map((invoice) => (
                  <TableRow key={invoice.id}>
                    <TableCell className="numeric font-medium">
                      {invoice.number}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {formatDate(invoice.period_start)} –{" "}
                      {formatDate(invoice.period_end)}
                    </TableCell>
                    <TableCell className="numeric text-right">
                      {formatMoney(invoice.amount_due, invoice.currency)}
                    </TableCell>
                    <TableCell>
                      {invoice.status === "paid" ? (
                        <Badge variant="outline" className="gap-1.5">
                          <CheckCircle2 className="size-3" /> Paid
                        </Badge>
                      ) : invoice.status === "open" ? (
                        <Badge variant="destructive">Unpaid</Badge>
                      ) : (
                        <Badge variant="secondary">{invoice.status}</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {invoice.paid_at ? formatDate(invoice.paid_at) : ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      </FadeIn>
    </div>
  );
}

function UsageRow({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number | null;
}) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  // Amber before the wall, not at it: discovering a plan ceiling at the
  // moment you need another till is a bad way to find out.
  const tight = limit !== null && pct >= 80;

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <dt className="text-muted-foreground">{label}</dt>
        <dd className="numeric">
          {used}
          {limit !== null ? ` / ${limit}` : " / unlimited"}
        </dd>
      </div>
      {limit !== null && (
        <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              tight ? "bg-amber-500" : "bg-primary",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}
