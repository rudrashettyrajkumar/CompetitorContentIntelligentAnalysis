import { api } from "../api";
import { Card, num } from "../components/ui";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";

export default function Competitors() {
  const { runId } = useRun();
  const profiles = useQuery(() => api.profiles(runId!), [runId]);

  return (
    <Page title="Competitors">
      <RunGate q={profiles}>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(profiles.data ?? []).map((p) => {
            const mix = Object.entries(p.content_mix).filter(([, v]) => v > 0);
            return (
              <Card key={p.competitor_id} title={p.competitor}>
                <p className="text-sm text-slate-700">{p.positioning_summary}</p>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <dt className="text-muted">Best format</dt>
                    <dd className="font-medium">{p.best_format ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Best topic</dt>
                    <dd className="font-medium">{p.best_topic ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Cadence</dt>
                    <dd className="font-medium">{num(p.posting_frequency_per_week, 1)}/week</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Windows</dt>
                    <dd className="font-medium">{p.engagement_windows.join(", ") || "—"}</dd>
                  </div>
                </dl>
                <div className="mt-3">
                  <div className="text-xs text-muted">Themes</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {p.primary_themes.map((t) => (
                      <span key={t} className="pill bg-indigo-100 text-indigo-800">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="mt-3 space-y-1">
                  <div className="text-xs text-muted">Content mix</div>
                  {mix.map(([group, pct]) => (
                    <div key={group} className="flex items-center gap-2 text-xs">
                      <span className="w-28 shrink-0 text-slate-600">{group}</span>
                      <div className="h-2 flex-1 rounded bg-slate-100">
                        <div className="h-2 rounded bg-brand" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="w-10 text-right tabular-nums text-slate-500">{pct}%</span>
                    </div>
                  ))}
                </div>
              </Card>
            );
          })}
        </div>
      </RunGate>
    </Page>
  );
}
