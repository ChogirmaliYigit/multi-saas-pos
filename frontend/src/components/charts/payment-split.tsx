"use client";

import type { PaymentBreakdown } from "@/lib/api/admin-types";
import { PAYMENT_COLORS, PAYMENT_LABELS } from "@/lib/charts/palette";
import { formatMoney } from "@/lib/format";

/**
 * How customers paid.
 *
 * Deliberately not a pie chart: humans compare angles badly, and with three
 * slices a labelled bar answers "how much of the take was cash" faster and
 * exactly. Every row is direct-labelled with its name and amount, so identity
 * never depends on colour alone.
 */
export function PaymentSplit({
  data,
  currency,
}: {
  data: PaymentBreakdown[];
  currency: string;
}) {
  const rows = data.map((row) => ({
    ...row,
    amount: Number.parseFloat(row.total),
  }));
  const total = rows.reduce((sum, row) => sum + row.amount, 0);

  if (total <= 0) {
    return (
      <p className="text-muted-foreground py-8 text-center text-sm">
        No payments in this period.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {/* One stacked bar for proportion, with a 2px surface gap between
          segments so adjacent fills never blur into a single block. */}
      <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full">
        {rows.map((row) => (
          <div
            key={row.method}
            style={{
              width: `${(row.amount / total) * 100}%`,
              backgroundColor: PAYMENT_COLORS[row.method] ?? "var(--muted)",
            }}
            className="first:rounded-l-full last:rounded-r-full"
          />
        ))}
      </div>

      <dl className="space-y-2.5">
        {rows.map((row) => (
          <div key={row.method} className="flex items-center gap-2.5 text-sm">
            <span
              aria-hidden
              className="size-2.5 shrink-0 rounded-[3px]"
              style={{
                backgroundColor: PAYMENT_COLORS[row.method] ?? "var(--muted)",
              }}
            />
            <dt className="min-w-0 flex-1 truncate">
              {PAYMENT_LABELS[row.method] ?? row.method}
              <span className="text-muted-foreground ml-1.5 text-xs">
                {row.count} {row.count === 1 ? "payment" : "payments"}
              </span>
            </dt>
            <dd className="numeric shrink-0 font-medium">
              {formatMoney(row.amount, currency)}
            </dd>
            <dd className="numeric text-muted-foreground w-11 shrink-0 text-right text-xs">
              {Math.round((row.amount / total) * 100)}%
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
