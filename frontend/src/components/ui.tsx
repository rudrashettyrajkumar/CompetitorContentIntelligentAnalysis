import type { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="p-6 text-sm text-muted">{label}</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      {message}
    </div>
  );
}

export function Empty({ label = "No data for this run." }: { label?: string }) {
  return <div className="card text-sm text-muted">{label}</div>;
}

export function Card({ title, actions, children }: { title?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="card">
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between">
          {title && <h3 className="text-sm font-semibold text-ink">{title}</h3>}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="card">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

const QUADRANT_STYLES: Record<string, string> = {
  high: "bg-emerald-100 text-emerald-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-600",
  high_freq_high_perf: "bg-emerald-100 text-emerald-800",
  low_freq_high_perf: "bg-indigo-100 text-indigo-800",
  high_freq_low_perf: "bg-amber-100 text-amber-800",
  low_freq_low_perf: "bg-slate-100 text-slate-600",
};

export function Pill({ children }: { children: string }) {
  const cls = QUADRANT_STYLES[children] || "bg-slate-100 text-slate-600";
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
            <tr key={i} className="hover:bg-slate-50">
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
