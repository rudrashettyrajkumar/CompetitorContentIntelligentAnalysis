import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { useRun } from "./runContext";
import Overview from "./pages/Overview";
import FormatsTopics from "./pages/FormatsTopics";
import Campaigns from "./pages/Campaigns";
import Competitors from "./pages/Competitors";
import Opportunities from "./pages/Opportunities";
import Calendar from "./pages/Calendar";
import Runs from "./pages/Runs";

const NAV = [
  { to: "/overview", label: "Overview" },
  { to: "/formats-topics", label: "Formats & Topics" },
  { to: "/campaigns", label: "Campaigns" },
  { to: "/competitors", label: "Competitors" },
  { to: "/opportunities", label: "Opportunities & Gaps" },
  { to: "/calendar", label: "Calendar" },
  { to: "/runs", label: "Runs" },
];

export default function App() {
  const { runs, runId, setRunId } = useRun();

  return (
    <div className="mx-auto flex min-h-screen max-w-[1400px] gap-6 p-6">
      <aside className="w-56 shrink-0">
        <div className="mb-4">
          <div className="text-sm font-semibold leading-tight text-ink">
            Competitor &amp; Content
          </div>
          <div className="text-xs text-muted">Intelligence Platform</div>
        </div>
        <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
          Run
        </label>
        <select
          className="mb-4 w-full rounded-lg border border-line bg-white px-2 py-1.5 text-sm"
          value={runId ?? ""}
          onChange={(e) => setRunId(Number(e.target.value))}
        >
          {runs.length === 0 && <option value="">no runs yet</option>}
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              #{r.id} · {r.period_days}d · {r.status}
            </option>
          ))}
        </select>
        <nav className="space-y-1">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) => `navlink ${isActive ? "navlink-active" : ""}`}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        {runId && (
          <div className="mt-6 space-y-1 text-xs">
            <a className="block text-brand hover:underline" href={api.exportUrl(runId, "json")}>
              Export JSON
            </a>
            <a className="block text-brand hover:underline" href={api.exportUrl(runId, "xlsx")}>
              Export XLSX
            </a>
          </div>
        )}
      </aside>

      <main className="min-w-0 flex-1">
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/formats-topics" element={<FormatsTopics />} />
          <Route path="/campaigns" element={<Campaigns />} />
          <Route path="/competitors" element={<Competitors />} />
          <Route path="/opportunities" element={<Opportunities />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </main>
    </div>
  );
}
