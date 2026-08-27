import { api } from "../api";
import { Card, Pill, Table, num } from "../components/ui";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";

export default function Opportunities() {
  const { runId } = useRun();
  const cross = useQuery(() => api.cross(runId!), [runId]);
  const opps = useQuery(() => api.opportunities(runId!), [runId]);
  const strategy = useQuery(() => api.strategy(runId!), [runId]);

  return (
    <Page title="Opportunities & Gaps">
      <RunGate q={[cross, opps, strategy]}>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="White spaces">
            <Table
              rows={cross.data?.white_spaces ?? []}
              columns={[
                { key: "t", header: "Topic", render: (w) => <span className="font-medium">{w.topic}</span> },
                { key: "r", header: "Reason", render: (w) => <Pill>{w.reason}</Pill> },
                { key: "c", header: "Competitors", render: (w) => w.competitors_covering },
                { key: "e", header: "Avg engagement", render: (w) => num(w.avg_engagement) },
              ]}
            />
          </Card>
          <Card title="Format opportunities">
            <Table
              rows={cross.data?.format_opportunities ?? []}
              columns={[
                { key: "f", header: "Format", render: (f) => <span className="font-medium">{f.format}</span> },
                { key: "s", header: "Share", render: (f) => `${(f.post_share * 100).toFixed(1)}%` },
                { key: "m", header: "Engagement multiplier", render: (f) => `${f.engagement_multiplier}×` },
              ]}
            />
          </Card>
        </div>

        <Card title="Keyword quadrants">
          <Table
            rows={(cross.data?.keyword_matrix ?? []).slice(0, 25)}
            columns={[
              { key: "t", header: "Term", render: (k) => <span className="font-medium">{k.term}</span> },
              { key: "f", header: "Frequency", render: (k) => k.frequency },
              { key: "e", header: "Avg engagement", render: (k) => num(k.avg_engagement) },
              { key: "q", header: "Quadrant", render: (k) => <Pill>{k.quadrant}</Pill> },
            ]}
          />
        </Card>

        {strategy.data && (
          <Card title="Recommended pillars & mix">
            <div className="grid gap-2 md:grid-cols-2">
              {strategy.data.pillars.map((p) => (
                <div key={p.name} className="rounded-lg border border-line p-3">
                  <div className="font-semibold text-ink">{p.name}</div>
                  <div className="text-xs text-slate-600">{p.description}</div>
                  <div className="mt-1 text-xs italic text-muted">{p.rationale}</div>
                </div>
              ))}
            </div>
            <div className="mt-2 text-xs text-muted">
              Cadence: {strategy.data.posting_cadence} · Windows:{" "}
              {strategy.data.engagement_windows.join(", ")}
            </div>
          </Card>
        )}

        <div className="grid gap-3 md:grid-cols-2">
          {(opps.data?.opportunities ?? []).map((o, i) => (
            <Card key={i}>
              <div className="flex items-center justify-between">
                <div className="font-semibold text-ink">{o.topic}</div>
                <div className="flex gap-1">
                  <Pill>{o.competitor_signal}</Pill>
                  <Pill>{o.engagement_potential}</Pill>
                </div>
              </div>
              <div className="text-xs text-muted">
                {o.pillar} · {o.recommended_format} · CTA {o.cta}
              </div>
              <p className="mt-2 text-sm font-medium">“{o.hook}”</p>
              <p className="mt-1 text-sm text-slate-700">{o.angle}</p>
              <p className="mt-1 text-xs text-muted">{o.key_message}</p>
              <ol className="mt-2 list-decimal pl-4 text-xs text-slate-600">
                {o.structure.map((s, j) => (
                  <li key={j}>{s}</li>
                ))}
              </ol>
            </Card>
          ))}
        </div>

        {opps.data && opps.data.originality_checks.some((c) => c.verdict !== "ok") && (
          <Card title="Originality guard">
            <ul className="text-xs text-slate-600">
              {opps.data.originality_checks
                .filter((c) => c.verdict !== "ok")
                .map((c, i) => (
                  <li key={i}>
                    opp #{c.opportunity_index} · {c.field}: <b>{c.verdict}</b> — {c.detail}
                  </li>
                ))}
            </ul>
          </Card>
        )}
      </RunGate>
    </Page>
  );
}
