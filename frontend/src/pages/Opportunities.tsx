import { api } from "../api";
import { Card, Pill, Table, num } from "../components/ui";
import { IconOpportunities, IconSpark } from "../components/icons";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";

export default function Opportunities() {
  const { runId } = useRun();
  const cross = useQuery(() => api.cross(runId!), [runId]);
  const opps = useQuery(() => api.opportunities(runId!), [runId]);
  const strategy = useQuery(() => api.strategy(runId!), [runId]);

  return (
    <Page
      title="Opportunities & Gaps"
      eyebrow="Where to play"
      description="White space the field is ignoring, formats that punch above their weight, and concrete post angles to run next."
    >
      <RunGate q={[cross, opps, strategy]}>
        <div className="grid gap-4 stagger lg:grid-cols-2">
          <Card title="White spaces" icon={<IconOpportunities size={15} />} hover>
            <Table
              rows={cross.data?.white_spaces ?? []}
              columns={[
                { key: "t", header: "Topic", render: (w) => <span className="font-medium text-ink">{w.topic}</span> },
                { key: "r", header: "Reason", render: (w) => <Pill>{w.reason}</Pill> },
                { key: "c", header: "Competitors", render: (w) => <span className="tnum">{w.competitors_covering}</span> },
                { key: "e", header: "Avg engagement", render: (w) => <span className="tnum">{num(w.avg_engagement)}</span> },
              ]}
            />
          </Card>
          <Card title="Format opportunities" icon={<IconSpark size={15} />} hover>
            <Table
              rows={cross.data?.format_opportunities ?? []}
              columns={[
                { key: "f", header: "Format", render: (f) => <span className="font-medium text-ink">{f.format}</span> },
                { key: "s", header: "Share", render: (f) => <span className="tnum">{(f.post_share * 100).toFixed(1)}%</span> },
                {
                  key: "m",
                  header: "Engagement multiplier",
                  render: (f) => (
                    <span className={`pill ${f.engagement_multiplier >= 1 ? "tag-ok" : "tag-neutral"}`}>
                      {f.engagement_multiplier}×
                    </span>
                  ),
                },
              ]}
            />
          </Card>
        </div>

        <Card title="Keyword quadrants" icon={<IconSpark size={15} />} className="mt-4" hover>
          <Table
            rows={(cross.data?.keyword_matrix ?? []).slice(0, 25)}
            columns={[
              { key: "t", header: "Term", render: (k) => <span className="font-medium text-ink">{k.term}</span> },
              { key: "f", header: "Frequency", render: (k) => <span className="tnum">{k.frequency}</span> },
              { key: "e", header: "Avg engagement", render: (k) => <span className="tnum">{num(k.avg_engagement)}</span> },
              { key: "q", header: "Quadrant", render: (k) => <Pill>{k.quadrant}</Pill> },
            ]}
          />
        </Card>

        {strategy.data && (
          <Card title="Recommended pillars & mix" icon={<IconOpportunities size={15} />} className="mt-4" hover>
            <div className="grid gap-2.5 md:grid-cols-2">
              {strategy.data.pillars.map((p, i) => (
                <div
                  key={p.name}
                  className="rounded-xl bg-ink/5 p-3 ring-1 ring-inset ring-line"
                  style={{ borderLeft: `3px solid ${["#818cf8", "#22d3ee", "#34d399", "#fbbf24", "#fb7185", "#c084fc"][i % 6]}` }}
                >
                  <div className="font-semibold text-ink">{p.name}</div>
                  <div className="mt-0.5 text-xs text-ink/70">{p.description}</div>
                  <div className="mt-1 text-xs italic text-muted">{p.rationale}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 text-xs text-muted">
              Cadence: <span className="text-ink/80">{strategy.data.posting_cadence}</span> · Windows:{" "}
              <span className="text-ink/80">{strategy.data.engagement_windows.join(", ")}</span>
            </div>
          </Card>
        )}

        <div className="mt-4 grid gap-3 stagger md:grid-cols-2">
          {(opps.data?.opportunities ?? []).map((o, i) => (
            <Card key={i} hover>
              <div className="flex items-start justify-between gap-3">
                <div className="font-semibold text-ink">{o.topic}</div>
                <div className="flex flex-wrap justify-end gap-1">
                  <Pill>{o.competitor_signal}</Pill>
                  <Pill>{o.engagement_potential}</Pill>
                </div>
              </div>
              <div className="mt-0.5 text-xs text-muted">
                {o.pillar} · {o.recommended_format} · CTA {o.cta}
              </div>
              <p className="mt-2.5 border-l-2 border-brand/50 pl-2.5 text-sm font-medium text-ink">
                &ldquo;{o.hook}&rdquo;
              </p>
              <p className="mt-1.5 text-sm text-ink/80">{o.angle}</p>
              <p className="mt-1 text-xs text-muted">{o.key_message}</p>
              <ol className="mt-2 list-decimal space-y-0.5 pl-4 text-xs text-ink/70">
                {o.structure.map((s, j) => (
                  <li key={j}>{s}</li>
                ))}
              </ol>
            </Card>
          ))}
        </div>

        {opps.data && opps.data.originality_checks.some((c) => c.verdict !== "ok") && (
          <Card title="Originality guard" className="mt-4">
            <ul className="space-y-1 text-xs text-ink/75">
              {opps.data.originality_checks
                .filter((c) => c.verdict !== "ok")
                .map((c, i) => (
                  <li key={i}>
                    opp #{c.opportunity_index} · {c.field}:{" "}
                    <b className="text-warn">{c.verdict}</b> — {c.detail}
                  </li>
                ))}
            </ul>
          </Card>
        )}
      </RunGate>
    </Page>
  );
}
