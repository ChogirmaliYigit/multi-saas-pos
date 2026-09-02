"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { RevenuePoint } from "@/lib/api/admin-types";
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
export function RevenueChart({
  data,
  currency,
}: {
  data: RevenuePoint[];
  currency: string;
}) {
  const points = data.map((point) => ({
    day: point.day,
    label: new Date(point.day).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
    }),
    revenue: Number.parseFloat(point.revenue),
    orders: point.orders,
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="revenue-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={PRIMARY_SERIES} stopOpacity={0.22} />
            <stop offset="100%" stopColor={PRIMARY_SERIES} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid {...gridProps} />
        <XAxis
          dataKey="label"
          {...axisTick}
          // A tick per day is unreadable at 30 days; every fifth keeps the
          // axis legible without hiding the range.
          interval={Math.max(0, Math.floor(points.length / 6) - 1)}
        />
        <YAxis
          {...axisTick}
          width={56}
          tickFormatter={(value: number) =>
            formatMoney(value, currency).replace(/\.00$/, "")
          }
        />
        <Tooltip
          cursor={{ stroke: "var(--chart-grid)", strokeWidth: 1 }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const point = payload[0].payload as (typeof points)[number];
            return (
              <ChartTooltipCard
                title={new Date(point.day).toLocaleDateString(undefined, {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                })}
                rows={[
                  {
                    label: "Revenue",
                    value: formatMoney(point.revenue, currency),
                    color: PRIMARY_SERIES,
                  },
                  { label: "Orders", value: String(point.orders) },
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
        <Area
          type="monotone"
          dataKey="revenue"
          stroke={PRIMARY_SERIES}
          strokeWidth={2}
          fill="url(#revenue-fill)"
          // 8px is the minimum a finger or an eye can find reliably.
          activeDot={{ r: 4.5, strokeWidth: 2, stroke: "var(--background)" }}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
