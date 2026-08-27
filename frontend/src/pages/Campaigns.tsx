import { useState } from "react";
import { api } from "../api";
import { Card, Empty, num } from "../components/ui";
import { IconArrowUpRight, IconCampaigns } from "../components/icons";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";

export default function Campaigns() {
  const { runId } = useRun();
  const campaigns = useQuery(() => api.campaigns(runId!), [runId]);
  const posts = useQuery(() => api.posts(runId!, "limit=100000"), [runId]);
  const [open, setOpen] = useState<number | null>(null);

  const postById = new Map((posts.data?.items ?? []).map((p) => [p.post_id, p]));

  return (
    <Page
      title="Campaigns"
      eyebrow="Coordinated pushes"
      description="Clusters of posts a competitor ran as one narrative — the theme, the objective, and how hard it landed."
    >
      <RunGate q={[campaigns, posts]}>
        {(campaigns.data ?? []).length === 0 && <Empty label="No campaigns detected for this run." />}
        <div className="grid gap-3 stagger md:grid-cols-2">
          {(campaigns.data ?? []).map((c) => (
            <Card key={c.id} hover>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-brand/14 text-brand">
                    <IconCampaigns size={16} />
                  </span>
                  <div>
                    <div className="font-semibold text-ink">{c.name}</div>
                    <div className="text-xs text-muted">{c.theme}</div>
                  </div>
                </div>
                <div className="text-right text-xs text-muted">
                  <div className="tnum text-sm font-semibold text-ink">{num(c.total_engagement)}</div>
                  <div>{c.post_ids.length} posts</div>
                </div>
              </div>
              {c.objective && <p className="mt-2.5 text-sm text-ink/85">{c.objective}</p>}
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {c.formats.map((f) => (
                  <span key={f} className="pill tag-neutral">
                    {f}
                  </span>
                ))}
              </div>
              <div className="mt-2 text-xs text-muted">
                {c.start_date?.slice(0, 10)} → {c.end_date?.slice(0, 10)} · CTA {c.cta ?? "—"}
              </div>
              {c.performance_summary && (
                <p className="mt-2 border-l-2 border-brand/40 pl-2.5 text-xs italic text-muted">
                  {c.performance_summary}
                </p>
              )}
              <button
                className="mt-2.5 text-xs font-medium text-brand hover:underline"
                onClick={() => setOpen(open === c.id ? null : c.id)}
              >
                {open === c.id ? "Hide" : "Show"} member posts
              </button>
              {open === c.id && (
                <ul className="mt-2 space-y-1 border-t border-line pt-2 text-xs">
                  {c.post_ids.map((pid) => {
                    const p = postById.get(pid);
                    return (
                      <li key={pid}>
                        {p ? (
                          <a
                            className="inline-flex items-center gap-1 text-brand hover:underline"
                            href={p.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {p.format} · {p.topic} · <span className="tnum">{num(p.engagement_score)}</span>
                            <IconArrowUpRight size={12} />
                          </a>
                        ) : (
                          <span className="text-muted">post #{pid}</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          ))}
        </div>
      </RunGate>
    </Page>
  );
}
