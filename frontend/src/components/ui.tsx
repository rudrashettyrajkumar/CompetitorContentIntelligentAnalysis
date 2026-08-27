import type { ReactNode } from "react";
import { IconTrendDown, IconTrendUp } from "./icons";
import { Sparkline } from "./charts";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label={label}>
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="card space-y-3">
          <div className="skeleton h-3 w-24" />
          <div className="skeleton h-7 w-32" />
          <div className="skeleton h-2 w-full" />
          <div className="skeleton h-2 w-2/3" />
        </div>
      ))}
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-bad/30 bg-bad/10 p-4 text-sm text-bad" role="alert">
      <span className="font-semibold">Something went wrong.</span> {message}
    </div>
  );
}

export function Empty({ label = "No data for this run." }: { label?: string }) {
  return (
    <div className="card flex items-center gap-3 text-sm text-muted">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-muted/10 text-muted">◦</span>
      {label}
    </div>
  );
}

export function Card({
  title,
  actions,
  children,
  hover = false,
  icon,
  className = "",
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  hover?: boolean;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`card ${hover ? "card-hover" : ""} ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && (
            <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
              {icon && <span className="text-brand">{icon}</span>}
              {title}
            </h3>
          )}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

export function StatTile({
  label,
  value,
  sub,
  icon,
  trend,
  spark,
  accent = "#818cf8",
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  icon?: ReactNode;
  trend?: number | null;
  spark?: number[];
  accent?: string;
}) {
  const up = trend != null && trend >= 0;
  return (
    <div className="card card-hover relative overflow-hidden">
      <div
        className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full opacity-40 blur-2xl"
        style={{ background: accent }}
        aria-hidden="true"
      />
      <div className="flex items-start justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</div>
        {icon && <span className="text-muted/80">{icon}</span>}
      </div>
      <div className="tnum mt-1.5 text-2xl font-semibold text-ink">{value}</div>
      <div className="mt-1 flex items-center gap-2">
        {trend != null && (
          <span className={`pill ${up ? "tag-ok" : "tag-bad"}`}>
            {up ? <IconTrendUp size={12} /> : <IconTrendDown size={12} />}
            {Math.abs(trend).toFixed(1)}%
          </span>
        )}
        {sub && <span className="text-xs text-muted">{sub}</span>}
      </div>
      {spark && spark.length > 1 && (
        <div className="mt-2 -mb-1">
          <Sparkline data={spark} color={accent} />
        </div>
      )}
    </div>
  );
}

const QUADRANT_STYLES: Record<string, string> = {
  high: "tag-ok",
  medium: "tag-warn",
  low: "tag-neutral",
  high_freq_high_perf: "tag-ok",
  low_freq_high_perf: "tag-brand",
  high_freq_low_perf: "tag-warn",
  low_freq_low_perf: "tag-neutral",
  ok: "tag-ok",
  valid: "tag-ok",
  invalid: "tag-bad",
  saturated: "tag-warn",
  untapped: "tag-brand",
  emerging: "tag-info",
};

export function Pill({ children }: { children: string }) {
  const cls = QUADRANT_STYLES[children] || "tag-neutral";
  return <span className={`pill ${cls}`}>{children.replace(/_/g, " ")}</span>;
}

export function Table<T>({
  rows,
  columns,
}: {
  rows: T[];
  columns: { key: string; header: string; render: (row: T) => ReactNode }[];
}) {
  if (!rows.length) return <Empty />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className="th">
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="transition-colors hover:bg-brand/5">
              {columns.map((c) => (
                <td key={c.key} className="td">
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function num(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}
