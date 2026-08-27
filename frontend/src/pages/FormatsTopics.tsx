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
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page, RunGate } from "./_shell";
import type { PerfRow } from "../types";

const QUAD_COLOR: Record<string, string> = {
  high_freq_high_perf: "#10b981",
  low_freq_high_perf: "#4f46e5",
  high_freq_low_perf: "#f59e0b",
  low_freq_low_perf: "#94a3b8",
};

export default function FormatsTopics() {
  const { runId } = useRun();
  const formats = useQuery(() => api.formats(runId!), [runId]);
  const topics = useQuery(() => api.topics(runId!), [runId]);
  const keywords = useQuery(() => api.keywords(runId!), [runId]);

  const perfCols = (label: string, key: "format" | "topic") => [
    { key: "name", header: label, render: (r: PerfRow) => <span className="font-medium">{r[key]}</span> },
    { key: "posts", header: "Posts", render: (r: PerfRow) => r.posts },
    { key: "avg", header: "Avg engagement", render: (r: PerfRow) => num(r.avg_engagement) },
    {
      key: "rate",
      header: "Avg rate",
      render: (r: PerfRow) => (r.avg_rate == null ? "—" : `${r.avg_rate.toFixed(2)}%`),
    },
    {
      key: "best",
      header: "Best post",
      render: (r: PerfRow) =>
        r.best_post ? (
          <a className="text-brand hover:underline" href={r.best_post} target="_blank" rel="noreferrer">
            {num(r.best_post_score)} ↗
          </a>
        ) : (
          "—"
        ),
    },
  ];

  return (
    <Page title="Formats & Topics">
      <RunGate q={[formats, topics, keywords]}>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Format performance">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={formats.data ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="format" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={70} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="avg_engagement" fill="#4f46e5" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-3">
              <Table rows={formats.data ?? []} columns={perfCols("Format", "format")} />
            </div>
          </Card>

          <Card title="Topic performance">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={topics.data ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="topic" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={70} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="avg_engagement" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-3">
              <Table rows={topics.data ?? []} columns={perfCols("Topic", "topic")} />
            </div>
          </Card>
        </div>

        <Card title="Keyword frequency vs. performance (frequency ≠ performance)">
          <ResponsiveContainer width="100%" height={320}>
            <ScatterChart margin={{ left: 10, right: 20, top: 10, bottom: 20 }}>
              <CartesianGrid stroke="#eef2f7" />
              <XAxis
                type="number"
                dataKey="frequency"
                name="frequency"
                tick={{ fontSize: 11 }}
                label={{ value: "frequency (posts)", position: "insideBottom", offset: -10, fontSize: 11 }}
              />
              <YAxis
                type="number"
                dataKey="avg_engagement"
                name="avg engagement"
                tick={{ fontSize: 11 }}
              />
              <ZAxis range={[60, 200]} />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                formatter={(v: number) => num(v)}
                labelFormatter={() => ""}
                content={({ payload }) =>
                  payload && payload[0] ? (
                    <div className="rounded border border-line bg-white p-2 text-xs shadow">
                      <div className="font-semibold">{payload[0].payload.term}</div>
                      <div>freq {payload[0].payload.frequency}</div>
                      <div>avg {num(payload[0].payload.avg_engagement)}</div>
                      <div className="mt-1">
                        <Pill>{payload[0].payload.quadrant}</Pill>
                      </div>
                    </div>
                  ) : null
                }
              />
              <Scatter data={keywords.data ?? []}>
                {(keywords.data ?? []).map((k, i) => (
                  <Cell key={i} fill={QUAD_COLOR[k.quadrant] || "#94a3b8"} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          <div className="mt-3">
            <Table
              rows={(keywords.data ?? []).slice(0, 20)}
              columns={[
                { key: "term", header: "Term", render: (k) => <span className="font-medium">{k.term}</span> },
                { key: "freq", header: "Frequency", render: (k) => k.frequency },
                { key: "avg", header: "Avg engagement", render: (k) => num(k.avg_engagement) },
                { key: "quad", header: "Quadrant", render: (k) => <Pill>{k.quadrant}</Pill> },
              ]}
            />
          </div>
        </Card>
      </RunGate>
    </Page>
  );
}
