/**
 * Frontend types mirroring the backend ORM models.
 * When the OpenAPI client is generated these will be replaced
 * by the auto-generated types from @case/shared/generated.
 */

/* ── Person ────────────────────────────────────── */
export interface Person {
  id: string;
  display_name: string;
  email: string | null;
  role: "admin" | "manager" | "member" | "bot";
  team: string | null;
  source_ids: Record<string, string | number>;
  created_at: string;
  updated_at: string;
}

/* ── Sprint ────────────────────────────────────── */
export type SprintStatus = "future" | "active" | "closed";

export interface Sprint {
  id: string;
  name: string;
  source: string;
  source_id: string;
  board_or_project: string | null;
  status: SprintStatus;
  start_date: string | null;
  end_date: string | null;
  goal: string | null;
  created_at: string;
  updated_at: string;
}

/* ── WorkItem ──────────────────────────────────── */
export type ItemType = "epic" | "story" | "task" | "bug" | "subtask";
export type ItemStatus = "open" | "in_progress" | "review" | "done" | "closed";
export type Priority = "critical" | "high" | "medium" | "low";

export interface ChangelogEntry {
  field: string;
  from: string;
  to: string;
  at: string;
}

export interface WorkItem {
  id: string;
  source: string;
  source_id: string;
  title: string;
  description: string | null;
  item_type: ItemType;
  status: ItemStatus;
  priority: Priority | null;
  story_points: number | null;
  due_date: string | null;
  resolved_at: string | null;
  assignee_id: string | null;
  sprint_id: string | null;
  parent_id: string | null;
  labels: string[];
  changelog: ChangelogEntry[];
  created_at: string;
  updated_at: string;
  // joined fields
  assignee?: Person;
  sprint?: Sprint;
}

/* ── EffortLog ─────────────────────────────────── */
export type EffortCategory =
  | "development"
  | "review"
  | "meeting"
  | "support"
  | "admin"
  | "other";

export interface EffortLog {
  id: string;
  person_id: string;
  day: string;
  hours: number;
  category: EffortCategory;
  description: string | null;
  work_item_id: string | null;
  source: string;
  created_at: string;
  // joined
  person?: Person;
  work_item?: WorkItem;
}

/* ── Report ────────────────────────────────────── */
export interface Report {
  id: string;
  period: "daily" | "weekly" | "monthly";
  period_start: string;
  period_end: string;
  title: string;
  summary: string | null;
  metrics: Record<string, unknown>;
  created_at: string;
}

/* ── Dashboard-specific types ──────────────────── */
export interface KpiSnapshot {
  label: string;
  value: number | string;
  previousValue?: number | string;
  unit?: string;
  trend?: "up" | "down" | "flat";
  trendIsPositive?: boolean;
}

export interface BurndownPoint {
  date: string;
  ideal: number;
  actual: number;
}

export interface VelocityPoint {
  sprint: string;
  committed: number;
  completed: number;
}

export interface CumulativeFlowPoint {
  date: string;
  open: number;
  in_progress: number;
  review: number;
  done: number;
}

export interface ThroughputPoint {
  week: string;
  count: number;
}

export interface LeadCyclePoint {
  date: string;
  lead_time_days: number;
  cycle_time_days: number;
}

/* ── Filter state ──────────────────────────────── */
export interface DashboardFilters {
  dateRange: { start: string; end: string };
  team: string | null;
  project: string | null;
  sprint: string | null;
}

/* ── Sprint report row ─────────────────────────── */
export type SprintItemCategory = "done" | "not_done" | "added_mid_sprint";

export interface SprintReportRow {
  item: WorkItem;
  category: SprintItemCategory;
}
