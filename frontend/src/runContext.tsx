import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Run } from "./types";

interface RunCtx {
  runs: Run[];
  runId: number | null;
  setRunId: (id: number) => void;
  activeRun: Run | null;
  reloadRuns: () => void;
}

const Ctx = createContext<RunCtx>({
  runs: [],
  runId: null,
  setRunId: () => {},
  activeRun: null,
  reloadRuns: () => {},
});

export function RunProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState<number | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    api
      .runs()
      .then((rs) => {
        setRuns(rs);
        setRunId((cur) => {
          if (cur && rs.some((r) => r.id === cur)) return cur;
          const done = rs.find((r) => r.status === "completed");
          return done ? done.id : rs[0]?.id ?? null;
        });
      })
      .catch(() => setRuns([]));
  }, [tick]);

  const value = useMemo<RunCtx>(
    () => ({
      runs,
      runId,
      setRunId,
      activeRun: runs.find((r) => r.id === runId) ?? null,
      reloadRuns: () => setTick((t) => t + 1),
    }),
    [runs, runId],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useRun = () => useContext(Ctx);
