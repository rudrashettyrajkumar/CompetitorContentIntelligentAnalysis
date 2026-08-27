import { useState } from "react";
import { api } from "../api";
import { Card, Empty } from "../components/ui";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";
import type { CalendarEntry } from "../types";

export default function Calendar() {
  const { runId } = useRun();
  const cal = useQuery(() => api.calendar(runId!), [runId]);
  const opps = useQuery(() => api.opportunities(runId!), [runId]);
  const [selected, setSelected] = useState<CalendarEntry | null>(null);

  const entries = cal.data?.calendar.entries ?? [];
  const byDay = new Map(entries.map((e) => [e.day, e]));
  const days = Array.from({ length: 30 }, (_, i) => i + 1);
  const pillars = [...new Set(entries.map((e) => e.pillar))];
  const pillarColor = (p: string) =>
    ["bg-indigo-100 text-indigo-800", "bg-sky-100 text-sky-800", "bg-emerald-100 text-emerald-800",
      "bg-amber-100 text-amber-800", "bg-rose-100 text-rose-800", "bg-violet-100 text-violet-800"][
      pillars.indexOf(p) % 6
    ];

  return (
    <Page title="30-Day Calendar">
      <RunGate q={[cal, opps]}>
        {entries.length === 0 ? (
          <Empty label="No calendar for this run." />
        ) : (
          <>
            <div className="mb-3 text-sm text-muted">
              {cal.data?.calendar.cadence_note}{" "}
              {cal.data?.valid ? (
                <span className="pill bg-emerald-100 text-emerald-800">valid</span>
              ) : (
                <span className="pill bg-rose-100 text-rose-800">invalid</span>
              )}
            </div>
            <div className="grid grid-cols-7 gap-2">
              {days.map((d) => {
                const e = byDay.get(d);
                return (
                  <button
                    key={d}
                    onClick={() => e && setSelected(e)}
                    className={`min-h-[84px] rounded-lg border border-line p-2 text-left ${
                      e ? "bg-white hover:ring-2 hover:ring-brand" : "bg-slate-50"
                    }`}
                  >
                    <div className="text-[10px] font-semibold text-muted">Day {d}</div>
                    {e && (
                      <div className="mt-1">
                        <div className={`pill ${pillarColor(e.pillar)}`}>{e.pillar}</div>
                        <div className="mt-1 text-[11px] text-slate-700">{e.topic}</div>
                        <div className="text-[10px] text-muted">{e.format}</div>
                      </div>
                    )}
                  </button>
                );
              })}
            </div>

            {selected && (
              <Card title={`Day ${selected.day} · ${selected.weekday}`}>
                <button
                  className="float-right text-xs text-brand hover:underline"
                  onClick={() => setSelected(null)}
                >
                  close
                </button>
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <dt className="text-xs text-muted">Pillar</dt>
                    <dd>{selected.pillar}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Topic</dt>
                    <dd>{selected.topic}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Format</dt>
                    <dd>{selected.format}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">CTA</dt>
                    <dd>{selected.cta}</dd>
                  </div>
                </dl>
                <p className="mt-2 text-sm">{selected.objective}</p>
                {selected.opportunity_ref != null && opps.data?.opportunities[selected.opportunity_ref] && (
                  <p className="mt-2 rounded bg-slate-50 p-2 text-xs text-slate-600">
                    Draws on opportunity: “{opps.data.opportunities[selected.opportunity_ref].hook}”
                  </p>
                )}
              </Card>
            )}
          </>
        )}
      </RunGate>
    </Page>
  );
}
