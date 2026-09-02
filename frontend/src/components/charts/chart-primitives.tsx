"use client";

/** Shared axis, grid and tooltip styling, so every chart reads as one system. */

export const gridProps = {
  strokeDasharray: "3 3",
  stroke: "var(--chart-grid)",
  // Recessive: the grid is a reading aid, never a mark competing with data.
  vertical: false,
} as const;

export const axisTick = {
  tickLine: false,
  axisLine: false,
  tick: { fill: "var(--muted-foreground)", fontSize: 11 },
  tickMargin: 8,
} as const;

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

/**
 * The tooltip is not optional garnish -- an HTML chart *is* interactive, and
 * without it the only way to read a value is to squint at the axis.
 *
 * Values wear text tokens; the colour appears as a swatch beside the label,
 * never as the text colour, so identity survives for anyone who cannot
 * separate the hues.
 */
export function ChartTooltipCard({
  title,
  rows,
}: {
  title: string;
  rows: TooltipRow[];
}) {
  return (
    <div className="bg-popover text-popover-foreground rounded-lg border px-3 py-2 shadow-md">
      <p className="mb-1 text-xs font-medium">{title}</p>
      <dl className="space-y-0.5">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center gap-2 text-xs">
            {row.color && (
              <span
                aria-hidden
                className="size-2 shrink-0 rounded-[2px]"
                style={{ backgroundColor: row.color }}
              />
            )}
            <dt className="text-muted-foreground">{row.label}</dt>
            <dd className="numeric ml-auto font-medium">{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
