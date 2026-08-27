import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Card, ErrorBox } from "../components/ui";
import { IconRuns } from "../components/icons";
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
    <Page
      title="Runs"
      eyebrow="Pipeline"
      description="Load competitors, kick off an intelligence run, and watch each stage land — or schedule the loop to run itself."
    >
      {err && <ErrorBox message={err} />}
      {msg && (
        <div className="mb-3 rounded-xl bg-ok/12 p-2.5 text-sm text-ok ring-1 ring-inset ring-ok/25">
          {msg}
        </div>
      )}

      <div className="grid gap-4 stagger lg:grid-cols-2">
        <Card title="1 · Upload competitors" icon={<StepDot n={1} />} hover>
          <p className="-mt-1 mb-3 text-xs text-muted">Excel (.xlsx) with the competitor list.</p>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx"
            className="block w-full text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-brand/15 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-brand hover:file:bg-brand/25"
          />
          <button className="btn-primary mt-3" onClick={upload}>
            Upload
          </button>
          <div className="mt-3 text-xs text-muted">
            <span className="tnum font-semibold text-ink">{(compsQ.data ?? []).length}</span> competitors stored
          </div>
        </Card>

        <Card title="2 · Start a run" icon={<StepDot n={2} />} hover>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-muted">
              Period (days)
              <select className="field mt-1" value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-muted">
              Adapter
              <select className="field mt-1" value={adapter} onChange={(e) => setAdapter(e.target.value)}>
                {ADAPTERS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="btn-primary"
              disabled={(compsQ.data ?? []).length === 0}
              onClick={start}
            >
              <IconRuns size={15} /> Start run
            </button>
          </div>
        </Card>
      </div>

      <Card title="Run history" className="mt-4">
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

function StepDot({ n }: { n: number }) {
  return (
    <span className="tnum grid h-6 w-6 place-items-center rounded-lg bg-brand/15 text-xs font-bold text-brand">
      {n}
    </span>
  );
}

function RunRow({ run, onOpen }: { run: Run; onOpen: () => void }) {
  const stages = run.stages;
  const doneIdx = run.status === "completed" ? stages.length : stages.indexOf(run.stage ?? "");
  return (
    <div className="rounded-xl bg-ink/[0.03] p-3 ring-1 ring-inset ring-line transition hover:ring-brand/40">
      <div className="flex items-center justify-between">
        <button className="text-sm font-semibold text-brand hover:underline" onClick={onOpen}>
          Run #{run.id}
        </button>
        <span
          className={`pill ${
            run.status === "completed"
              ? "tag-ok"
              : run.status === "failed"
                ? "tag-bad"
                : "tag-warn"
          }`}
        >
          {run.status === "running" && (
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
          )}
          {run.status}
          {run.stage ? ` · ${run.stage}` : ""}
        </span>
      </div>
      <div className="mt-2 flex gap-1">
        {stages.map((s, i) => (
          <div
            key={s}
            title={`${s}${run.stage_timings[s] ? ` ${run.stage_timings[s]}s` : ""}`}
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/10"
          >
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: run.status === "failed" && i === doneIdx ? "100%" : i < doneIdx ? "100%" : "0%",
                backgroundImage:
                  run.status === "failed" && i === doneIdx
                    ? "linear-gradient(90deg,#f87171,#ef4444)"
                    : "linear-gradient(90deg,#6366f1,#a855f7)",
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1.5 text-[11px] text-muted">
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
    <Card title="Schedules · recurring intelligence loop" className="mt-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-muted">
          Cron
          <input className="field mt-1 tnum" value={cron} onChange={(e) => setCron(e.target.value)} />
        </label>
        <label className="text-xs text-muted">
          Period
          <select className="field mt-1" value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
            {PERIODS.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <button
          className="btn-primary"
          onClick={() =>
            api
              .createSchedule({ cron, period_days: period, adapter: "mock", enabled: true })
              .then(load)
          }
        >
          Add weekly schedule
        </button>
      </div>
      <ul className="mt-3 space-y-1.5 text-sm">
        {(schedules ?? []).map((s) => (
          <li
            key={s.id}
            className="flex items-center justify-between rounded-xl bg-ink/[0.03] px-3 py-2 ring-1 ring-inset ring-line"
          >
            <span className="text-ink/80">
              <code className="tnum rounded bg-ink/8 px-1.5 py-0.5 text-xs">{s.cron}</code> · {s.period_days}d ·{" "}
              {s.adapter} ·{" "}
              <span className={s.enabled ? "text-ok" : "text-muted"}>
                {s.enabled ? "enabled" : "disabled"}
              </span>
              {s.next_run_at ? ` · next ${s.next_run_at.slice(0, 16).replace("T", " ")}` : ""}
            </span>
            <button
              className="text-xs font-medium text-bad hover:underline"
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
