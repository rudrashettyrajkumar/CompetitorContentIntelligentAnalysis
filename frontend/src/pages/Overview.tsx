import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { Card, StatTile, num } from "../components/ui";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { CHART_COLORS, Page, RunGate } from "./_shell";

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
    <Page title="Overview">
      <RunGate q={[summary, profiles, posts]}>
        {summary.data && (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile label="Competitors" value={summary.data.competitors_analyzed} />
            <StatTile
              label="Posts"
              value={num(summary.data.total_posts)}
              sub={`${summary.data.posts_per_week}/week`}
            />
            <StatTile label="Avg engagement" value={num(summary.data.avg_engagement_score)} />
            <StatTile
              label="Avg rate"
              value={summary.data.avg_engagement_rate == null ? "—" : `${summary.data.avg_engagement_rate.toFixed(2)}%`}
            />
            <StatTile label="Top competitor" value={summary.data.top_competitor ?? "—"} />
            <StatTile label="Top topic" value={summary.data.top_topic ?? "—"} />
            <StatTile label="Top format" value={summary.data.top_format ?? "—"} />
            <StatTile label="Campaigns" value={summary.data.campaign_count} />
          </div>
        )}

        {diff.data?.diff && (
          <div className="mt-4 card border-indigo-200 bg-indigo-50">
            <h3 className="text-sm font-semibold text-indigo-900">What changed since the last run</h3>
            <p className="mt-1 text-sm text-indigo-800">
              {diff.data.change_report?.narrative ??
                `${num(diff.data.diff.new_posts)} new posts (${diff.data.diff.posts_delta_pct}% change), ` +
                  `${diff.data.diff.new_campaigns.length} new campaigns, ` +
                  `${diff.data.diff.emerging_keywords.length} emerging keywords.`}
            </p>
            {diff.data.diff.strategy_refresh_recommended && (
              <p className="mt-2 text-xs font-medium text-indigo-900">
                Strategy refresh recommended: {diff.data.diff.refresh_reasons.join("; ")}
              </p>
            )}
          </div>
        )}

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Card title="Engagement over time (per competitor)">
            <EngagementChart posts={posts.data?.items ?? []} />
          </Card>
          <Card title="Posts per week">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={profiles.data ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="competitor" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="posting_frequency_per_week" fill="#4f46e5" name="posts/week" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      </RunGate>
    </Page>
  );
}

function EngagementChart({ posts }: { posts: { competitor_name: string; posted_at: string; engagement_score: number }[] }) {
  const weeks = new Map<string, Record<string, number>>();
  const competitors = new Set<string>();
  for (const p of posts) {
    const wk = isoWeek(new Date(p.posted_at));
    competitors.add(p.competitor_name);
    const row = weeks.get(wk) ?? { week: wk } as unknown as Record<string, number>;
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
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
        <XAxis dataKey="week" tick={{ fontSize: 10 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {names.map((n, i) => (
          <Line key={n} type="monotone" dataKey={n} stroke={CHART_COLORS[i % CHART_COLORS.length]} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
