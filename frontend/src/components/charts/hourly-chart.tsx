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

import type { SalesByHour } from "@/lib/api/admin-types";
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
export function HourlyChart({
  data,
  currency,
}: {
  data: SalesByHour[];
  currency: string;
}) {
  const rows = data.map((point) => ({
    hour: point.hour,
    label: `${String(point.hour).padStart(2, "0")}:00`,
    revenue: Number.parseFloat(point.revenue),
    orders: point.orders,
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="label" {...axisTick} interval={2} />
        <YAxis
          {...axisTick}
          width={52}
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
                title={`${row.label}–${String(row.hour + 1).padStart(2, "0")}:00`}
                rows={[
                  {
                    label: "Revenue",
                    value: formatMoney(row.revenue, currency),
                    color: PRIMARY_SERIES,
                  },
                  { label: "Orders", value: String(row.orders) },
                ]}
              />
            );
          }}
        />
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
          fill={PRIMARY_SERIES}
          radius={[4, 4, 0, 0]}
          maxBarSize={18}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
