"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TopProduct } from "@/lib/api/admin-types";
import { PRIMARY_SERIES } from "@/lib/charts/palette";
import { formatMoney } from "@/lib/format";

import { ChartTooltipCard, axisTick, gridProps } from "./chart-primitives";

{
  /*
  Mount animation off. Recharts drives it with requestAnimationFrame
  behind an expanding clipPath, so whenever rAF is throttled -- a
  background tab, low power mode, a wall-mounted tablet that was
  just re-focused -- the clip stays collapsed and the data is simply
  not drawn. It also ignores prefers-reduced-motion. The card already
  fades in; the numbers inside it should just be there.
*/
}
export function TopProductsChart({
  data,
  currency,
}: {
  data: TopProduct[];
  currency: string;
}) {
  const rows = data
    .map((item) => ({
      name: item.name,
      sku: item.sku ?? "",
      revenue: Number.parseFloat(item.revenue),
      quantity: Number.parseFloat(item.quantity_sold),
    }))
    .reverse(); // recharts draws bottom-up; biggest belongs at the top

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, rows.length * 34)}>
      <BarChart
        data={rows}
        layout="vertical"
        margin={{ top: 4, right: 16, bottom: 4, left: 0 }}
        barCategoryGap={6}
      >
        <CartesianGrid {...gridProps} horizontal={false} vertical />
        <XAxis
          type="number"
          {...axisTick}
          tickFormatter={(value: number) =>
            formatMoney(value, currency).replace(/\.00$/, "")
          }
        />
        <YAxis
          type="category"
          dataKey="name"
          {...axisTick}
          width={132}
          tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
        />
        <Tooltip
          cursor={{ fill: "var(--muted)", opacity: 0.4 }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as (typeof rows)[number];
            return (
              <ChartTooltipCard
                title={row.name}
                rows={[
                  {
                    label: "Revenue",
                    value: formatMoney(row.revenue, currency),
                    color: PRIMARY_SERIES,
                  },
                  { label: "Units", value: String(row.quantity) },
                  ...(row.sku ? [{ label: "SKU", value: row.sku }] : []),
                ]}
              />
            );
          }}
        />
        {/* 4px rounded end anchored to the baseline: the bar grows from zero,
            so only the far end is rounded. */}
        {/*
          Mount animation off. Recharts drives it with requestAnimationFrame
          behind an expanding clipPath, so whenever rAF is throttled -- a
          background tab, low power mode, a wall-mounted tablet that was
          just re-focused -- the clip stays collapsed and the data is simply
          not drawn. It also ignores prefers-reduced-motion. The card already
          fades in; the numbers inside it should just be there.
        */}
        <Bar
          dataKey="revenue"
          radius={[0, 4, 4, 0]}
          maxBarSize={22}
          isAnimationActive={false}
        >
          {rows.map((row) => (
            <Cell key={row.name} fill={PRIMARY_SERIES} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
