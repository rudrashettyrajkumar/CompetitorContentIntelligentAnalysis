import type { ReactNode } from "react";
import { useRun } from "../runContext";
import { Empty, ErrorBox, Loading } from "../components/ui";
import type { QueryState } from "../hooks";
import { SERIES } from "../components/charts";

export function Page({
  title,
  eyebrow = "Intelligence",
  description,
  actions,
  children,
}: {
  title: string;
  eyebrow?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="animate-fade-up">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="h-eyebrow">{eyebrow}</div>
          <h1 className="title-gradient mt-1 text-2xl font-bold sm:text-[1.75rem]">{title}</h1>
          {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
        </div>
        {actions}
      </div>
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

export const CHART_COLORS = SERIES;
