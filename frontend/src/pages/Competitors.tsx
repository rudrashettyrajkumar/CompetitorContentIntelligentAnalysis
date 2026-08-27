import { api } from "../api";
import { Card, num } from "../components/ui";
import { IconCompetitors } from "../components/icons";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";

export default function Competitors() {
  const { runId } = useRun();
  const profiles = useQuery(() => api.profiles(runId!), [runId]);

  return (
    <Page
      title="Competitors"
      eyebrow="Positioning"
      description="A one-card read on each rival — how they position, what they post, how often, and when their audience shows up."
    >
      <RunGate q={profiles}>
        <div className="grid gap-3 stagger md:grid-cols-2 xl:grid-cols-3">
          {(profiles.data ?? []).map((p) => {
            const mix = Object.entries(p.content_mix).filter(([, v]) => v > 0);
            return (
              <Card key={p.competitor_id} hover>
                <div className="flex items-center gap-2.5">
                  <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand/25 to-brand2/20 text-brand">
                    <IconCompetitors size={17} />
                  </span>
                  <h3 className="font-semibold text-ink">{p.competitor}</h3>
                </div>
                <p className="mt-2.5 text-sm text-ink/80">{p.positioning_summary}</p>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
                  <Field label="Best format" value={p.best_format} />
                  <Field label="Best topic" value={p.best_topic} />
                  <Field label="Cadence" value={`${num(p.posting_frequency_per_week, 1)}/week`} />
                  <Field label="Windows" value={p.engagement_windows.join(", ") || "—"} />
                </dl>
                <div className="mt-3">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Themes</div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {p.primary_themes.map((t) => (
                      <span key={t} className="pill tag-brand">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="mt-3 space-y-1.5">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Content mix</div>
                  {mix.map(([group, pct]) => (
                    <div key={group} className="flex items-center gap-2 text-xs">
                      <span className="w-28 shrink-0 text-muted">{group}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink/8">
                        <div
                          className="h-2 rounded-full"
                          style={{
                            width: `${pct}%`,
                            backgroundImage: "linear-gradient(90deg,#6366f1,#a855f7)",
                          }}
                        />
                      </div>
                      <span className="tnum w-9 text-right text-muted">{pct}%</span>
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

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-lg bg-ink/5 px-2.5 py-1.5">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium text-ink">{value ?? "—"}</dd>
    </div>
  );
}
