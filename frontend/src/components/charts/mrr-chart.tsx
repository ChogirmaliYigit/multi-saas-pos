"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MrrPoint } from "@/lib/api/platform-types";
import { PRIMARY_SERIES } from "@/lib/charts/palette";
import { formatMoney } from "@/lib/format";

import { ChartTooltipCard, axisTick, gridProps } from "./chart-primitives";

/**
 * Recurring revenue by month.
 *
 * Bars rather than a line: MRR is a discrete monthly figure, and a line
 * implies a continuous value that existed between the points. One series, so
 * one hue and no legend.
 */
export function MrrChart({
  data,
  currency,
}: {
  data: MrrPoint[];
  currency: string;
}) {
  const rows = data.map((point) => ({
    month: point.month,
    label: new Date(point.month).toLocaleDateString(undefined, {
      month: "short",
      year: "2-digit",
    }),
    mrr: Number.parseFloat(point.mrr),
    tenants: point.tenants,
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="label" {...axisTick} />
        <YAxis
          {...axisTick}
          width={60}
          tickFormatter={(value: number) =>
            formatMoney(value, currency).replace(/\.00$/, "")
          }
        />
        <Tooltip
          cursor={{ fill: "var(--muted)", opacity: 0.4 }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as (typeof rows)[number];
            return (
              <ChartTooltipCard
                title={new Date(row.month).toLocaleDateString(undefined, {
                  month: "long",
                  year: "numeric",
                })}
                rows={[
                  {
                    label: "MRR",
                    value: formatMoney(row.mrr, currency),
                    color: PRIMARY_SERIES,
                  },
                  { label: "Paying shops", value: String(row.tenants) },
                ]}
              />
            );
          }}
        />
        {/*
          Mount animation off, for the same reason as every other chart here:
          recharts drives it with requestAnimationFrame behind an expanding
          clipPath, so a throttled tab simply never draws the data.
        */}
        <Bar
          dataKey="mrr"
          fill={PRIMARY_SERIES}
          radius={[4, 4, 0, 0]}
          maxBarSize={36}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
