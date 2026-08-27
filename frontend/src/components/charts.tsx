import type { ReactNode } from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";

/** Vivid series palette tuned to read on both the light and dark glass surfaces. */
export const SERIES = [
  "#818cf8",
  "#22d3ee",
  "#34d399",
  "#fbbf24",
  "#fb7185",
  "#c084fc",
  "#2dd4bf",
  "#f472b6",
];

/** Shared axis props — CSS in index.css colors the ticks/gridlines per theme. */
export const axisProps = {
  tick: { fontSize: 11 } as const,
  tickLine: false,
  axisLine: false,
} as const;

export const gridProps = {
  strokeDasharray: "4 4",
  vertical: false,
} as const;

/** <defs> with a soft vertical gradient per series index, id `grad-{i}`. */
export function ChartGradients({ ids = SERIES.length }: { ids?: number }) {
  return (
    <defs>
      {Array.from({ length: ids }, (_, i) => (
        <linearGradient key={i} id={`grad-${i}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={SERIES[i % SERIES.length]} stopOpacity={0.45} />
          <stop offset="100%" stopColor={SERIES[i % SERIES.length]} stopOpacity={0.02} />
        </linearGradient>
      ))}
      <linearGradient id="grad-bar" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#a5b4fc" stopOpacity={0.95} />
        <stop offset="100%" stopColor="#6366f1" stopOpacity={0.55} />
      </linearGradient>
    </defs>
  );
}

/** Frosted tooltip that matches the glass cards. */
export function GlassTooltip({
  active,
  payload,
  label,
  fmt = (v) => String(v),
  title,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number | string; color?: string; dataKey?: string | number }[];
  label?: string | number;
  fmt?: (v: number | string) => string;
  title?: ReactNode;
}) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="glass glass-raised min-w-[9rem] rounded-xl px-3 py-2 text-xs">
      <div className="mb-1 font-semibold text-ink">{title ?? label}</div>
      <div className="space-y-1">
        {payload.map((p, i) => (
          <div key={i} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-muted">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: p.color ?? SERIES[i % SERIES.length] }}
              />
              {p.name ?? p.dataKey}
            </span>
            <span className="tnum font-medium text-ink">
              {p.value == null ? "—" : fmt(p.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Tiny inline trend sparkline for stat tiles. */
export function Sparkline({
  data,
  color = SERIES[0],
  height = 40,
}: {
  data: number[];
  color?: string;
  height?: number;
}) {
  if (!data || data.length < 2) return null;
  const rows = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={rows} margin={{ top: 4, bottom: 0, left: 0, right: 0 }}>
        <defs>
          <linearGradient id={`spark-${color}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.4} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={2}
          fill={`url(#spark-${color})`}
          isAnimationActive={false}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
