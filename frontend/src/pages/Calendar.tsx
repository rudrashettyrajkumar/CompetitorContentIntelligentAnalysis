import { useState } from "react";
import { api } from "../api";
import { Card, Empty } from "../components/ui";
import { IconClose } from "../components/icons";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";
import type { CalendarEntry } from "../types";

const PALETTE = ["#818cf8", "#22d3ee", "#34d399", "#fbbf24", "#fb7185", "#c084fc", "#2dd4bf", "#f472b6"];

export default function Calendar() {
  const { runId } = useRun();
  const cal = useQuery(() => api.calendar(runId!), [runId]);
  const opps = useQuery(() => api.opportunities(runId!), [runId]);
  const [selected, setSelected] = useState<CalendarEntry | null>(null);

  const entries = cal.data?.calendar.entries ?? [];
  const byDay = new Map(entries.map((e) => [e.day, e]));
  const days = Array.from({ length: 30 }, (_, i) => i + 1);
  const pillars = [...new Set(entries.map((e) => e.pillar))];
  const colorFor = (p: string) => PALETTE[pillars.indexOf(p) % PALETTE.length];

  return (
    <Page
      title="30-Day Calendar"
      eyebrow="Execution plan"
      description="A ready-to-run publishing schedule — each day mapped to a pillar, a topic, a format, and an objective."
    >
      <RunGate q={[cal, opps]}>
        {entries.length === 0 ? (
          <Empty label="No calendar for this run." />
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className="text-sm text-muted">{cal.data?.calendar.cadence_note}</span>
              <span className={`pill ${cal.data?.valid ? "tag-ok" : "tag-bad"}`}>
                {cal.data?.valid ? "valid" : "invalid"}
              </span>
              <div className="flex flex-wrap gap-2">
                {pillars.map((p) => (
                  <span key={p} className="inline-flex items-center gap-1.5 text-xs text-muted">
                    <span className="h-2 w-2 rounded-full" style={{ background: colorFor(p) }} />
                    {p}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
              {days.map((d) => {
                const e = byDay.get(d);
                const c = e ? colorFor(e.pillar) : undefined;
                return (
                  <button
                    key={d}
                    onClick={() => e && setSelected(e)}
                    disabled={!e}
                    className={`group relative min-h-[92px] overflow-hidden rounded-xl p-2.5 text-left transition ${
                      e
                        ? "glass card-hover cursor-pointer"
                        : "border border-dashed border-line bg-transparent opacity-60"
                    } ${selected?.day === d ? "ring-2 ring-brand" : ""}`}
                  >
                    {e && (
                      <span
                        className="absolute inset-y-0 left-0 w-1"
                        style={{ background: c }}
                        aria-hidden="true"
                      />
                    )}
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">
                      Day {d}
                    </div>
                    {e && (
                      <div className="mt-1.5">
                        <span
                          className="pill"
                          style={{
                            background: `${c}22`,
                            color: c,
                            boxShadow: `inset 0 0 0 1px ${c}55`,
                          }}
                        >
                          {e.pillar}
                        </span>
                        <div className="mt-1 text-[11px] font-medium text-ink">{e.topic}</div>
                        <div className="text-[10px] text-muted">{e.format}</div>
                      </div>
                    )}
                  </button>
                );
              })}
            </div>

            {selected && (
              <Card
                title={`Day ${selected.day} · ${selected.weekday}`}
                className="mt-4"
                actions={
                  <button className="btn-ghost !px-2 !py-1.5" onClick={() => setSelected(null)} aria-label="Close">
                    <IconClose size={15} />
                  </button>
                }
              >
                <dl className="grid grid-cols-2 gap-2.5 text-sm sm:grid-cols-4">
                  <Detail label="Pillar" value={selected.pillar} accent={colorFor(selected.pillar)} />
                  <Detail label="Topic" value={selected.topic} />
                  <Detail label="Format" value={selected.format} />
                  <Detail label="CTA" value={selected.cta} />
                </dl>
                <p className="mt-3 text-sm text-ink/85">{selected.objective}</p>
                {selected.opportunity_ref != null &&
                  opps.data?.opportunities[selected.opportunity_ref] && (
                    <p className="mt-3 rounded-xl bg-brand/8 p-2.5 text-xs text-ink/75 ring-1 ring-inset ring-brand/20">
                      Draws on opportunity: &ldquo;
                      {opps.data.opportunities[selected.opportunity_ref].hook}&rdquo;
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

function Detail({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-lg bg-ink/5 px-2.5 py-1.5">
      <dt className="text-[11px] uppercase tracking-wider text-muted">{label}</dt>
      <dd className="font-medium text-ink" style={accent ? { color: accent } : undefined}>
        {value}
      </dd>
    </div>
  );
}
