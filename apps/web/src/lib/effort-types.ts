/** Shared TypeScript types for the effort / timesheet feature. */

export type EffortCategory =
  | "development"
  | "review"
  | "meeting"
  | "support"
  | "admin"
  | "other";

export const EFFORT_CATEGORIES: EffortCategory[] = [
  "development",
  "review",
  "meeting",
  "support",
  "admin",
  "other",
];

export const CATEGORY_COLORS: Record<EffortCategory, string> = {
  development: "#3b82f6",
  review: "#8b5cf6",
  meeting: "#f59e0b",
  support: "#10b981",
  admin: "#6b7280",
  other: "#ef4444",
};

export interface EffortLogEntry {
  id: string;
  person_id: string;
  day: string;
  hours: number;
  category: EffortCategory;
  description: string | null;
  work_item_id: string | null;
  planned_hours: number | null;
  locked: boolean;
  source: string;
  extra: Record<string, unknown> | null;
  created_at: string;
}

export interface DaySummary {
  day: string;
  total_hours: number;
  planned_hours: number | null;
  by_category: Partial<Record<EffortCategory, number>>;
}

export interface TeamMemberEffort {
  person_id: string;
  display_name: string;
  total_hours: number;
  by_category: Partial<Record<EffortCategory, number>>;
}

export interface TeamEffortResponse {
  team_id: string;
  from_date: string;
  to_date: string;
  total_hours: number;
  by_category: Partial<Record<EffortCategory, number>>;
  by_day: DaySummary[];
  members: TeamMemberEffort[];
}

export interface SprintEffortResponse {
  sprint_id: string;
  sprint_name: string;
  total_effort_hours: number;
  by_category: Partial<Record<EffortCategory, number>>;
  total_story_points: number | null;
  items_done: number;
  items_total: number;
}
