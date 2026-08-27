// Hand-kept mirror of the FastAPI response models (EPIC-07).

export interface Competitor {
  id: number;
  name: string;
  linkedin_url: string;
  industry: string | null;
  market: string | null;
  priority: string;
  status: string;
}

export interface Run {
  id: number;
  status: "pending" | "running" | "completed" | "failed";
  stage: string | null;
  adapter: string;
  period_days: number;
  trigger: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  stage_timings: Record<string, number>;
  stages: string[];
}

export interface Summary {
  run_id: number;
  period_days: number;
  competitors_analyzed: number;
  total_posts: number;
  posts_per_week: number;
  avg_engagement_score: number;
  avg_engagement_rate: number | null;
  top_competitor: string | null;
  top_topic: string | null;
  top_format: string | null;
  top_keywords: string[];
  campaign_count: number;
}

export interface PostRow {
  post_id: number;
  competitor_id: number;
  competitor_name: string;
  url: string;
  posted_at: string;
  format: string | null;
  topic: string | null;
  cta: string | null;
  keywords: string[];
  engagement_score: number;
  engagement_rate: number | null;
}

export interface Paged<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface PerfRow {
  posts: number;
  avg_engagement: number;
  avg_rate: number | null;
  best_post: string | null;
  best_post_score: number | null;
  format?: string;
  topic?: string;
  cta?: string;
}

export interface KeywordPerf {
  term: string;
  frequency: number;
  avg_engagement: number;
  quadrant: string;
}

export interface Campaign {
  id: number;
  competitor_id: number;
  name: string;
  theme: string | null;
  objective: string | null;
  post_ids: number[];
  start_date: string | null;
  end_date: string | null;
  formats: string[];
  keywords: string[];
  hashtags: string[];
  cta: string | null;
  target_audience: string | null;
  total_engagement: number | null;
  performance_summary: string | null;
}

export interface Profile {
  competitor_id: number;
  competitor: string;
  primary_themes: string[];
  content_mix: Record<string, number>;
  best_format: string | null;
  best_topic: string | null;
  posting_frequency_per_week: number;
  engagement_windows: string[];
  positioning_summary: string;
}

export interface CrossInsights {
  common_themes: { topic: string; competitors_covering: number; post_share: number; avg_engagement: number }[];
  saturated_topics: { topic: string; competitors_covering: number; post_share: number }[];
  white_spaces: { topic: string; reason: string; competitors_covering: number; avg_engagement: number }[];
  opportunity_topics: { topic: string; avg_engagement: number; post_share: number; engagement_vs_median: number }[];
  format_opportunities: { format: string; post_share: number; avg_engagement: number; engagement_multiplier: number }[];
  keyword_matrix: KeywordPerf[];
}

export interface WhyItWorked {
  hook: string;
  structure: string;
  visual_format: string;
  cta_assessment: string;
  audience_relevance: string;
  length_note: string;
  summary: string;
}

export interface TopContent {
  ranked_by: string;
  items: {
    rank: number;
    competitor: string;
    url: string;
    format: string | null;
    topic: string | null;
    engagement_score: number;
    engagement_rate: number | null;
    why: WhyItWorked;
  }[];
}

export interface Strategy {
  pillars: { name: string; description: string; rationale: string }[];
  content_mix: Record<string, number>;
  recommended_formats: { format: string; share: number; rationale: string }[];
  posting_cadence: string;
  engagement_windows: string[];
}

export interface Opportunity {
  topic: string;
  pillar: string;
  competitor_signal: string;
  competition_level: string;
  engagement_potential: string;
  recommended_format: string;
  target_audience: string;
  hook: string;
  angle: string;
  key_message: string;
  structure: string[];
  cta: string;
  keywords: string[];
  hashtags: string[];
}

export interface OpportunitiesPayload {
  opportunities: Opportunity[];
  originality_checks: { field: string; opportunity_index: number; verdict: string; detail: string }[];
}

export interface CalendarEntry {
  day: number;
  weekday: string;
  pillar: string;
  topic: string;
  format: string;
  objective: string;
  cta: string;
  opportunity_ref: number | null;
}

export interface CalendarPayload {
  calendar: { entries: CalendarEntry[]; cadence_note: string };
  valid: boolean;
  errors: string[];
}

export interface DiffPayload {
  diff: PeriodDiff | null;
  change_report: { narrative: string } | null;
}

export interface PeriodDiff {
  baseline_run_id: number;
  current_run_id: number;
  new_posts: number;
  posts_delta_pct: number;
  new_campaigns: string[];
  ended_campaigns: string[];
  emerging_keywords: { term: string; before: number; after: number; growth: number }[];
  fading_keywords: { term: string; before: number; after: number; growth: number }[];
  topic_performance_shifts: { topic: string; before: number; after: number; delta: number }[];
  format_shifts: { format: string; before: number; after: number; delta: number }[];
  profile_changes: { competitor: string; field: string; before: string; after: string }[];
  strategy_refresh_recommended: boolean;
  refresh_reasons: string[];
}

export interface Schedule {
  id: number;
  cron: string;
  period_days: number;
  adapter: string;
  enabled: boolean;
  last_run_id: number | null;
  next_run_at: string | null;
}
