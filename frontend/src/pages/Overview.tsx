import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { Card, StatTile, num } from "../components/ui";
import {
  ChartGradients,
  GlassTooltip,
  SERIES,
  axisProps,
  gridProps,
} from "../components/charts";
import {
  IconCampaigns,
  IconCompetitors,
  IconFormats,
  IconOpportunities,
  IconRuns,
  IconSpark,
} from "../components/icons";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";

function isoWeek(d: Date): string {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - dayNum + 3);
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
  const week =
    1 +
    Math.round(
      ((date.getTime() - firstThursday.getTime()) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) /
        7,
    );
  return `${date.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

export default function Overview() {
  const { runId } = useRun();
  const summary = useQuery(() => api.summary(runId!), [runId]);
  const profiles = useQuery(() => api.profiles(runId!), [runId]);
  const posts = useQuery(() => api.posts(runId!, "limit=100000&sort=posted_at&order=asc"), [runId]);
  const diff = useQuery(() => api.diff(runId!), [runId]);

  return (
    <Page
      title="Overview"
      eyebrow="Snapshot"
      description="Where every tracked competitor stands this period — volume, engagement, and what moved since the last run."
    >
      <RunGate q={[summary, profiles, posts]}>
        {summary.data && (
          <div className="grid grid-cols-2 gap-3 stagger md:grid-cols-4">
            <StatTile
              label="Competitors"
              value={summary.data.competitors_analyzed}
              icon={<IconCompetitors size={16} />}
              accent={SERIES[0]}
            />
            <StatTile
              label="Posts"
              value={num(summary.data.total_posts)}
              sub={`${summary.data.posts_per_week}/week`}
              icon={<IconRuns size={16} />}
              accent={SERIES[1]}
            />
            <StatTile
              label="Avg engagement"
              value={num(summary.data.avg_engagement_score)}
              icon={<IconSpark size={16} />}
              accent={SERIES[2]}
            />
            <StatTile
              label="Avg rate"
              value={
                summary.data.avg_engagement_rate == null
                  ? "—"
                  : `${summary.data.avg_engagement_rate.toFixed(2)}%`
              }
              icon={<IconSpark size={16} />}
              accent={SERIES[3]}
            />
            <StatTile
              label="Top competitor"
              value={<span className="text-base">{summary.data.top_competitor ?? "—"}</span>}
              icon={<IconCompetitors size={16} />}
              accent={SERIES[5]}
            />
            <StatTile
              label="Top topic"
              value={<span className="text-base">{summary.data.top_topic ?? "—"}</span>}
              icon={<IconOpportunities size={16} />}
              accent={SERIES[6]}
            />
            <StatTile
              label="Top format"
              value={<span className="text-base">{summary.data.top_format ?? "—"}</span>}
              icon={<IconFormats size={16} />}
              accent={SERIES[1]}
            />
            <StatTile
              label="Campaigns"
              value={summary.data.campaign_count}
              icon={<IconCampaigns size={16} />}
              accent={SERIES[4]}
            />
          </div>
        )}

        {diff.data?.diff && (
          <div className="relative mt-4 card card-hover overflow-hidden">
            <div
              className="pointer-events-none absolute inset-x-0 top-0 h-px"
              style={{ background: "linear-gradient(90deg,transparent,#818cf8,transparent)" }}
            />
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand/15 text-brand">
                <IconSpark size={15} />
              </span>
              <h3 className="text-sm font-semibold text-ink">What changed since the last run</h3>
            </div>
            <p className="mt-2 text-sm text-ink/80">
              {diff.data.change_report?.narrative ??
                `${num(diff.data.diff.new_posts)} new posts (${diff.data.diff.posts_delta_pct}% change), ` +
                  `${diff.data.diff.new_campaigns.length} new campaigns, ` +
                  `${diff.data.diff.emerging_keywords.length} emerging keywords.`}
            </p>
            {diff.data.diff.strategy_refresh_recommended && (
              <p className="mt-2 inline-flex rounded-lg bg-warn/12 px-2.5 py-1 text-xs font-medium text-warn ring-1 ring-inset ring-warn/25">
                Strategy refresh recommended: {diff.data.diff.refresh_reasons.join("; ")}
              </p>
            )}
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              {diff.data.diff.emerging_keywords.length > 0 && (
                <DeltaBars
                  title="Emerging keywords (before → after)"
                  data={diff.data.diff.emerging_keywords.map((k) => ({
                    label: k.term,
                    before: k.before,
                    after: k.after,
                  }))}
                />
              )}
              {diff.data.diff.topic_performance_shifts.length > 0 && (
                <DeltaBars
                  title="Topic engagement shifts"
                  data={diff.data.diff.topic_performance_shifts.map((t) => ({
                    label: t.topic,
                    before: t.before,
                    after: t.after,
                  }))}
                />
              )}
            </div>
          </div>
        )}

        <div className="mt-4 grid gap-4 stagger lg:grid-cols-2">
          <Card title="Engagement over time" icon={<IconSpark size={15} />} hover>
            <EngagementChart posts={posts.data?.items ?? []} />
          </Card>
          <Card title="Posting cadence by competitor" icon={<IconRuns size={15} />} hover>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={profiles.data ?? []} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <ChartGradients />
                <CartesianGrid {...gridProps} />
                <XAxis
                  dataKey="competitor"
                  {...axisProps}
                  interval={0}
                  angle={-20}
                  textAnchor="end"
                  height={64}
                />
                <YAxis {...axisProps} />
                <Tooltip
                  cursor={{ fill: "rgb(129 140 248 / 0.08)" }}
                  content={<GlassTooltip fmt={(v) => num(Number(v), 1)} />}
                />
                <Bar
                  dataKey="posting_frequency_per_week"
                  fill="url(#grad-bar)"
                  name="posts/week"
                  radius={[6, 6, 0, 0]}
                  maxBarSize={46}
                />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      </RunGate>
    </Page>
  );
}

function DeltaBars({
  title,
  data,
}: {
  title: string;
  data: { label: string; before: number; after: number }[];
}) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-muted">{title}</div>
      <ResponsiveContainer width="100%" height={Math.max(120, data.length * 36)}>
        <BarChart data={data.slice(0, 6)} layout="vertical" margin={{ left: 8, right: 12 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="label" width={92} {...axisProps} />
          <Tooltip cursor={{ fill: "rgb(129 140 248 / 0.08)" }} content={<GlassTooltip />} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Bar dataKey="before" fill="#64748b" name="before" radius={[0, 4, 4, 0]} maxBarSize={12} />
          <Bar dataKey="after" fill="#818cf8" name="after" radius={[0, 4, 4, 0]} maxBarSize={12} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function EngagementChart({
  posts,
}: {
  posts: { competitor_name: string; posted_at: string; engagement_score: number }[];
}) {
  const weeks = new Map<string, Record<string, number>>();
  const competitors = new Set<string>();
  for (const p of posts) {
    const wk = isoWeek(new Date(p.posted_at));
    competitors.add(p.competitor_name);
    const row = weeks.get(wk) ?? ({ week: wk } as unknown as Record<string, number>);
    (row as Record<string, unknown>)["week"] = wk;
    row[p.competitor_name] = (row[p.competitor_name] ?? 0) + p.engagement_score;
    weeks.set(wk, row);
  }
  const data = [...weeks.values()].sort((a, b) =>
    String((a as Record<string, unknown>).week).localeCompare(String((b as Record<string, unknown>).week)),
  );
  const names = [...competitors];
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <ChartGradients ids={names.length} />
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="week" {...axisProps} />
        <YAxis {...axisProps} />
        <Tooltip content={<GlassTooltip fmt={(v) => num(Number(v))} />} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {names.map((n, i) => (
          <Area
            key={n}
            type="monotone"
            dataKey={n}
            stroke={SERIES[i % SERIES.length]}
            strokeWidth={2}
            fill={`url(#grad-${i})`}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
