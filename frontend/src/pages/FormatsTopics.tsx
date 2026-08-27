import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { api } from "../api";
import { Card, Pill, Table, num } from "../components/ui";
import { ChartGradients, GlassTooltip, axisProps, gridProps } from "../components/charts";
import { IconArrowUpRight, IconFormats, IconOpportunities } from "../components/icons";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";
import type { PerfRow } from "../types";

const QUAD_COLOR: Record<string, string> = {
  high_freq_high_perf: "#34d399",
  low_freq_high_perf: "#818cf8",
  high_freq_low_perf: "#fbbf24",
  low_freq_low_perf: "#64748b",
};

export default function FormatsTopics() {
  const { runId } = useRun();
  const formats = useQuery(() => api.formats(runId!), [runId]);
  const topics = useQuery(() => api.topics(runId!), [runId]);
  const keywords = useQuery(() => api.keywords(runId!), [runId]);

  const perfCols = (label: string, key: "format" | "topic") => [
    { key: "name", header: label, render: (r: PerfRow) => <span className="font-medium text-ink">{r[key]}</span> },
    { key: "posts", header: "Posts", render: (r: PerfRow) => <span className="tnum">{r.posts}</span> },
    { key: "avg", header: "Avg engagement", render: (r: PerfRow) => <span className="tnum">{num(r.avg_engagement)}</span> },
    {
      key: "rate",
      header: "Avg rate",
      render: (r: PerfRow) => (
        <span className="tnum">{r.avg_rate == null ? "—" : `${r.avg_rate.toFixed(2)}%`}</span>
      ),
    },
    {
      key: "best",
      header: "Best post",
      render: (r: PerfRow) =>
        r.best_post ? (
          <a
            className="inline-flex items-center gap-1 font-medium text-brand hover:underline"
            href={r.best_post}
            target="_blank"
            rel="noreferrer"
          >
            <span className="tnum">{num(r.best_post_score)}</span>
            <IconArrowUpRight size={13} />
          </a>
        ) : (
          "—"
        ),
    },
  ];

  return (
    <Page
      title="Formats & Topics"
      eyebrow="Performance"
      description="Which content shapes and subjects actually earn engagement — and where volume is being spent without return."
    >
      <RunGate q={[formats, topics, keywords]}>
        <div className="grid gap-4 stagger lg:grid-cols-2">
          <Card title="Format performance" icon={<IconFormats size={15} />} hover>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={formats.data ?? []} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <ChartGradients />
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="format" {...axisProps} interval={0} angle={-25} textAnchor="end" height={70} />
                <YAxis {...axisProps} />
                <Tooltip cursor={{ fill: "rgb(129 140 248 / 0.08)" }} content={<GlassTooltip fmt={(v) => num(Number(v))} />} />
                <Bar dataKey="avg_engagement" fill="url(#grad-bar)" radius={[6, 6, 0, 0]} maxBarSize={44} />
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-3">
              <Table rows={formats.data ?? []} columns={perfCols("Format", "format")} />
            </div>
          </Card>

          <Card title="Topic performance" icon={<IconOpportunities size={15} />} hover>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={topics.data ?? []} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="grad-topic" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#67e8f9" stopOpacity={0.95} />
                    <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.5} />
                  </linearGradient>
                </defs>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="topic" {...axisProps} interval={0} angle={-25} textAnchor="end" height={70} />
                <YAxis {...axisProps} />
                <Tooltip cursor={{ fill: "rgb(34 211 238 / 0.08)" }} content={<GlassTooltip fmt={(v) => num(Number(v))} />} />
                <Bar dataKey="avg_engagement" fill="url(#grad-topic)" radius={[6, 6, 0, 0]} maxBarSize={44} />
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-3">
              <Table rows={topics.data ?? []} columns={perfCols("Topic", "topic")} />
            </div>
          </Card>
        </div>

        <Card
          title="Keyword frequency vs. performance"
          icon={<IconSparkInline />}
          className="mt-4"
          hover
        >
          <p className="-mt-1 mb-2 text-xs text-muted">
            Top-left is the sweet spot: talked about rarely, but engages strongly. High frequency ≠ high performance.
          </p>
          <ResponsiveContainer width="100%" height={320}>
            <ScatterChart margin={{ left: 4, right: 20, top: 10, bottom: 24 }}>
              <CartesianGrid stroke="rgb(148 163 190 / 0.18)" />
              <XAxis
                type="number"
                dataKey="frequency"
                name="frequency"
                {...axisProps}
                label={{ value: "frequency (posts)", position: "insideBottom", offset: -12, fontSize: 11 }}
              />
              <YAxis type="number" dataKey="avg_engagement" name="avg engagement" {...axisProps} />
              <ZAxis range={[70, 260]} />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                content={({ payload }) =>
                  payload && payload[0] ? (
                    <div className="glass glass-raised rounded-xl px-3 py-2 text-xs">
                      <div className="font-semibold text-ink">{payload[0].payload.term}</div>
                      <div className="mt-1 text-muted">
                        freq <span className="tnum text-ink">{payload[0].payload.frequency}</span> · avg{" "}
                        <span className="tnum text-ink">{num(payload[0].payload.avg_engagement)}</span>
                      </div>
                      <div className="mt-1.5">
                        <Pill>{payload[0].payload.quadrant}</Pill>
                      </div>
                    </div>
                  ) : null
                }
              />
              <Scatter data={keywords.data ?? []} fillOpacity={0.85}>
                {(keywords.data ?? []).map((k, i) => (
                  <Cell key={i} fill={QUAD_COLOR[k.quadrant] || "#64748b"} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          <div className="mt-3">
            <Table
              rows={(keywords.data ?? []).slice(0, 20)}
              columns={[
                { key: "term", header: "Term", render: (k) => <span className="font-medium text-ink">{k.term}</span> },
                { key: "freq", header: "Frequency", render: (k) => <span className="tnum">{k.frequency}</span> },
                { key: "avg", header: "Avg engagement", render: (k) => <span className="tnum">{num(k.avg_engagement)}</span> },
                { key: "quad", header: "Quadrant", render: (k) => <Pill>{k.quadrant}</Pill> },
              ]}
            />
          </div>
        </Card>
      </RunGate>
    </Page>
  );
}

function IconSparkInline() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="7" cy="16" r="2" />
      <circle cx="17" cy="8" r="2" />
      <path d="M9 15 15 9" />
    </svg>
  );
}
