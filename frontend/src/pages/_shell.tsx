import type { ReactNode } from "react";
import { useRun } from "../runContext";
import { Empty, ErrorBox, Loading } from "../components/ui";
import type { QueryState } from "../hooks";

export function Page({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-ink">{title}</h1>
      {children}
    </div>
  );
}

export function RunGate({
  q,
  children,
}: {
  q: QueryState<unknown> | QueryState<unknown>[];
  children: ReactNode;
}) {
  const { runId } = useRun();
  const queries = Array.isArray(q) ? q : [q];
  if (!runId) return <Empty label="Start a run on the Runs page to see intelligence here." />;
  const err = queries.find((x) => x.error)?.error;
  if (err) return <ErrorBox message={err} />;
  if (queries.some((x) => x.loading && !x.data)) return <Loading />;
  return <>{children}</>;
}

export const CHART_COLORS = [
  "#4f46e5",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#14b8a6",
  "#ec4899",
];
