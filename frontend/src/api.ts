import type {
  CalendarPayload,
  Campaign,
  Competitor,
  CrossInsights,
  DiffPayload,
  KeywordPerf,
  OpportunitiesPayload,
  Paged,
  PerfRow,
  PostRow,
  Profile,
  Run,
  Schedule,
  Strategy,
  Summary,
  TopContent,
} from "./types";

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.title || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  competitors: () => j<Competitor[]>("/api/competitors"),
  deleteCompetitor: (id: number) =>
    j<void>(`/api/competitors/${id}`, { method: "DELETE" }),
  uploadCompetitors: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/competitors/upload", { method: "POST", body: form });
    if (!res.ok) throw new Error(`${res.status} ${(await res.json()).detail || res.statusText}`);
    return res.json();
  },

  runs: () => j<Run[]>("/api/runs"),
  run: (id: number) => j<Run>(`/api/runs/${id}`),
  startRun: (body: { period_days: number; adapter: string; competitor_ids?: number[] }) =>
    j<Run>("/api/runs", { method: "POST", body: JSON.stringify(body) }),

  summary: (r: number) => j<Summary>(`/api/results/${r}/summary`),
  posts: (r: number, qs: string) => j<Paged<PostRow>>(`/api/results/${r}/posts?${qs}`),
  formats: (r: number) => j<PerfRow[]>(`/api/results/${r}/formats`),
  topics: (r: number) => j<PerfRow[]>(`/api/results/${r}/topics`),
  keywords: (r: number) => j<KeywordPerf[]>(`/api/results/${r}/keywords`),
  campaigns: (r: number) => j<Campaign[]>(`/api/results/${r}/campaigns`),
  profiles: (r: number) => j<Profile[]>(`/api/results/${r}/profiles`),
  cross: (r: number) => j<CrossInsights>(`/api/results/${r}/cross`),
  topContent: (r: number) => j<TopContent>(`/api/results/${r}/top-content`),
  strategy: (r: number) => j<Strategy>(`/api/results/${r}/strategy`),
  opportunities: (r: number) => j<OpportunitiesPayload>(`/api/results/${r}/opportunities`),
  calendar: (r: number) => j<CalendarPayload>(`/api/results/${r}/calendar`),
  diff: (r: number) => j<DiffPayload>(`/api/results/${r}/diff`),

  schedules: () => j<Schedule[]>("/api/schedule"),
  createSchedule: (body: { cron: string; period_days: number; adapter: string; enabled: boolean }) =>
    j<Schedule>("/api/schedule", { method: "POST", body: JSON.stringify(body) }),
  deleteSchedule: (id: number) => j<void>(`/api/schedule/${id}`, { method: "DELETE" }),

  exportUrl: (r: number, kind: "json" | "xlsx") => `/api/exports/${r}.${kind}`,
};
