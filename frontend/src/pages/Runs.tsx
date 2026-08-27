import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Card, ErrorBox } from "../components/ui";
import { useQuery } from "../hooks";
import { useRun } from "../runContext";
import { Page } from "./_shell";
import type { Run, Schedule } from "../types";

const PERIODS = [7, 10, 30, 60, 90];
const ADAPTERS = ["mock", "import", "apify"];

export default function Runs() {
  const { reloadRuns, setRunId } = useRun();
  const runsQ = useQuery(() => api.runs(), []);
  const compsQ = useQuery(() => api.competitors(), []);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [period, setPeriod] = useState(30);
  const [adapter, setAdapter] = useState("mock");
  const fileRef = useRef<HTMLInputElement>(null);

  const active = (runsQ.data ?? []).some((r) => r.status === "pending" || r.status === "running");
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => runsQ.reload(), 1500);
    return () => clearInterval(id);
  }, [active, runsQ]);

  async function upload() {
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    setErr(null);
    try {
      const r = await api.uploadCompetitors(f);
      setMsg(`Uploaded: ${r.accepted} accepted, ${r.rejected.length} rejected.`);
      compsQ.reload();
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }

  async function start() {
    setErr(null);
    try {
      const run = await api.startRun({ period_days: period, adapter });
      setMsg(`Run #${run.id} started.`);
      setRunId(run.id);
      runsQ.reload();
      reloadRuns();
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }

  return (
    <Page title="Runs">
      {err && <ErrorBox message={err} />}
      {msg && <div className="mb-3 rounded-lg bg-emerald-50 p-2 text-sm text-emerald-700">{msg}</div>}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="1 · Upload competitors (Excel)">
          <input ref={fileRef} type="file" accept=".xlsx" className="block w-full text-sm" />
          <button
            className="mt-3 rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white"
            onClick={upload}
          >
            Upload
          </button>
          <div className="mt-3 text-xs text-muted">
            {(compsQ.data ?? []).length} competitors stored
          </div>
        </Card>

        <Card title="2 · Start a run">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-muted">
              Period (days)
              <select
                className="mt-1 block rounded-lg border border-line px-2 py-1.5 text-sm"
                value={period}
                onChange={(e) => setPeriod(Number(e.target.value))}
              >
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-muted">
              Adapter
              <select
                className="mt-1 block rounded-lg border border-line px-2 py-1.5 text-sm"
                value={adapter}
                onChange={(e) => setAdapter(e.target.value)}
              >
                {ADAPTERS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              disabled={(compsQ.data ?? []).length === 0}
              onClick={start}
            >
              Start run
            </button>
          </div>
        </Card>
      </div>

      <Card title="Run history">
        <div className="space-y-2">
          {(runsQ.data ?? []).map((r) => (
            <RunRow key={r.id} run={r} onOpen={() => setRunId(r.id)} />
          ))}
          {(runsQ.data ?? []).length === 0 && <div className="text-sm text-muted">No runs yet.</div>}
        </div>
      </Card>

      <SchedulePanel />
    </Page>
  );
}

function RunRow({ run, onOpen }: { run: Run; onOpen: () => void }) {
  const stages = run.stages;
  const doneIdx = run.status === "completed" ? stages.length : stages.indexOf(run.stage ?? "");
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="flex items-center justify-between">
        <button className="text-sm font-medium text-brand hover:underline" onClick={onOpen}>
          Run #{run.id}
        </button>
        <span
          className={`pill ${
            run.status === "completed"
              ? "bg-emerald-100 text-emerald-800"
              : run.status === "failed"
                ? "bg-rose-100 text-rose-800"
                : "bg-amber-100 text-amber-800"
          }`}
        >
          {run.status}
          {run.stage ? ` · ${run.stage}` : ""}
        </span>
      </div>
      <div className="mt-2 flex gap-1">
        {stages.map((s, i) => (
          <div
            key={s}
            title={`${s}${run.stage_timings[s] ? ` ${run.stage_timings[s]}s` : ""}`}
            className={`h-1.5 flex-1 rounded ${
              run.status === "failed" && i === doneIdx
                ? "bg-rose-400"
                : i < doneIdx
                  ? "bg-brand"
                  : "bg-slate-200"
            }`}
          />
        ))}
      </div>
      <div className="mt-1 text-[11px] text-muted">
        {run.adapter} · {run.period_days}d · {run.trigger}
        {run.error ? ` · ${run.error.split("\n")[0]}` : ""}
      </div>
    </div>
  );
}

function SchedulePanel() {
  const [schedules, setSchedules] = useState<Schedule[] | null>(null);
  const [supported, setSupported] = useState(true);
  const [cron, setCron] = useState("0 6 * * 1");
  const [period, setPeriod] = useState(30);

  const load = () =>
    api
      .schedules()
      .then(setSchedules)
      .catch(() => setSupported(false));
  useEffect(() => {
    load();
  }, []);

  if (!supported) return null;

  return (
    <Card title="Schedules (recurring intelligence loop)">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-muted">
          Cron
          <input
            className="mt-1 block rounded-lg border border-line px-2 py-1.5 text-sm"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
          />
        </label>
        <label className="text-xs text-muted">
          Period
          <select
            className="mt-1 block rounded-lg border border-line px-2 py-1.5 text-sm"
            value={period}
            onChange={(e) => setPeriod(Number(e.target.value))}
          >
            {PERIODS.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <button
          className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white"
          onClick={() =>
            api
              .createSchedule({ cron, period_days: period, adapter: "mock", enabled: true })
              .then(load)
          }
        >
          Add weekly schedule
        </button>
      </div>
      <ul className="mt-3 space-y-1 text-sm">
        {(schedules ?? []).map((s) => (
          <li key={s.id} className="flex items-center justify-between rounded border border-line px-2 py-1">
            <span>
              <code className="text-xs">{s.cron}</code> · {s.period_days}d · {s.adapter} ·{" "}
              {s.enabled ? "enabled" : "disabled"}
              {s.next_run_at ? ` · next ${s.next_run_at.slice(0, 16).replace("T", " ")}` : ""}
            </span>
            <button
              className="text-xs text-rose-600 hover:underline"
              onClick={() => api.deleteSchedule(s.id).then(load)}
            >
              delete
            </button>
          </li>
        ))}
        {schedules?.length === 0 && <li className="text-xs text-muted">No schedules.</li>}
      </ul>
    </Card>
  );
}
