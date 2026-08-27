import { useState } from "react";
import { api } from "../api";
import { Card, Empty, num } from "../components/ui";
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
    <Page title="Campaigns">
      <RunGate q={[campaigns, posts]}>
        {(campaigns.data ?? []).length === 0 && <Empty label="No campaigns detected for this run." />}
        <div className="grid gap-3 md:grid-cols-2">
          {(campaigns.data ?? []).map((c) => (
            <Card key={c.id}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold text-ink">{c.name}</div>
                  <div className="text-xs text-muted">{c.theme}</div>
                </div>
                <div className="text-right text-xs text-muted">
                  <div>{num(c.total_engagement)} engagement</div>
                  <div>{c.post_ids.length} posts</div>
                </div>
              </div>
              {c.objective && <p className="mt-2 text-sm">{c.objective}</p>}
              <div className="mt-2 flex flex-wrap gap-1">
                {c.formats.map((f) => (
                  <span key={f} className="pill bg-slate-100 text-slate-600">
                    {f}
                  </span>
                ))}
              </div>
              <div className="mt-1 text-xs text-muted">
                {c.start_date?.slice(0, 10)} → {c.end_date?.slice(0, 10)} · CTA {c.cta ?? "—"}
              </div>
              {c.performance_summary && (
                <p className="mt-2 text-xs italic text-muted">{c.performance_summary}</p>
              )}
              <button
                className="mt-2 text-xs font-medium text-brand hover:underline"
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
                          <a className="text-brand hover:underline" href={p.url} target="_blank" rel="noreferrer">
                            {p.format} · {p.topic} · {num(p.engagement_score)} ↗
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
