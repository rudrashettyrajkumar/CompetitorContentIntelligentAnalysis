import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { useRun } from "./runContext";
import { useTheme } from "./theme";
import {
  IconCalendar,
  IconCampaigns,
  IconClose,
  IconCompetitors,
  IconDownload,
  IconFormats,
  IconMenu,
  IconMoon,
  IconOpportunities,
  IconOverview,
  IconRuns,
  IconSun,
} from "./components/icons";
import Overview from "./pages/Overview";
import FormatsTopics from "./pages/FormatsTopics";
import Campaigns from "./pages/Campaigns";
import Competitors from "./pages/Competitors";
import Opportunities from "./pages/Opportunities";
import Calendar from "./pages/Calendar";
import Runs from "./pages/Runs";

const NAV = [
  { to: "/overview", label: "Overview", icon: IconOverview },
  { to: "/formats-topics", label: "Formats & Topics", icon: IconFormats },
  { to: "/campaigns", label: "Campaigns", icon: IconCampaigns },
  { to: "/competitors", label: "Competitors", icon: IconCompetitors },
  { to: "/opportunities", label: "Opportunities & Gaps", icon: IconOpportunities },
  { to: "/calendar", label: "Calendar", icon: IconCalendar },
  { to: "/runs", label: "Runs", icon: IconRuns },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <div
        className="grid h-9 w-9 place-items-center rounded-xl text-white shadow-lg"
        style={{ backgroundImage: "linear-gradient(135deg,#6366f1,#a855f7)" }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 18 9 11l4 4 7-9" />
          <circle cx="9" cy="11" r="1.6" fill="currentColor" />
          <circle cx="13" cy="15" r="1.6" fill="currentColor" />
        </svg>
      </div>
      <div className="leading-tight">
        <div className="font-display text-sm font-bold text-ink">Competitor Intel</div>
        <div className="text-[11px] text-muted">Content Intelligence</div>
      </div>
    </div>
  );
}

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      className="btn-ghost !px-2.5 !py-2"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    >
      {theme === "dark" ? <IconSun size={16} /> : <IconMoon size={16} />}
    </button>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { runs, runId, setRunId } = useRun();
  const active = runs.find((r) => r.id === runId);

  return (
    <div className="flex h-full flex-col gap-5 p-4">
      <div className="flex items-center justify-between">
        <Brand />
        <button
          className="btn-ghost !px-2 !py-2 lg:hidden"
          onClick={onNavigate}
          aria-label="Close menu"
        >
          <IconClose size={16} />
        </button>
      </div>

      <div>
        <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-muted">
          Active run
        </label>
        <select
          className="field"
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
        {active && (
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-muted">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                active.status === "completed"
                  ? "bg-ok"
                  : active.status === "failed"
                    ? "bg-bad"
                    : "bg-warn animate-pulse"
              }`}
            />
            {active.status}
            {active.stage ? ` · ${active.stage}` : ""}
          </div>
        )}
      </div>

      <nav className="space-y-1">
        {NAV.map((n) => {
          const Icon = n.icon;
          return (
            <NavLink
              key={n.to}
              to={n.to}
              onClick={onNavigate}
              className={({ isActive }) => `navlink ${isActive ? "navlink-active" : ""}`}
            >
              <Icon size={17} />
              {n.label}
            </NavLink>
          );
        })}
      </nav>

      <div className="mt-auto space-y-2">
        {runId && (
          <div className="card !p-3">
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
              Export run #{runId}
            </div>
            <div className="flex gap-2">
              <a className="btn-ghost flex-1 !px-2 !py-1.5 text-xs" href={api.exportUrl(runId, "json")}>
                <IconDownload size={14} /> JSON
              </a>
              <a className="btn-ghost flex-1 !px-2 !py-1.5 text-xs" href={api.exportUrl(runId, "xlsx")}>
                <IconDownload size={14} /> XLSX
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [open, setOpen] = useState(false);

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[1500px] gap-6 p-4 sm:p-6">
      {/* Desktop sidebar */}
      <aside className="sticky top-6 hidden h-[calc(100dvh-3rem)] w-64 shrink-0 lg:block">
        <div className="glass glass-raised h-full overflow-y-auto rounded-3xl">
          <Sidebar />
        </div>
      </aside>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div className="glass glass-raised absolute left-0 top-0 h-full w-72 animate-fade-up overflow-y-auto rounded-r-3xl">
            <Sidebar onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}

      <main className="min-w-0 flex-1">
        {/* Mobile top bar */}
        <div className="mb-4 flex items-center justify-between lg:hidden">
          <button className="btn-ghost !px-2.5 !py-2" onClick={() => setOpen(true)} aria-label="Open menu">
            <IconMenu size={18} />
          </button>
          <Brand />
          <ThemeToggle />
        </div>

        {/* Desktop top bar */}
        <div className="mb-5 hidden items-center justify-end lg:flex">
          <ThemeToggle />
        </div>

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
