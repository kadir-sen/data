/**
 * Mock data for dashboard development.
 * Replace with real API calls via the OpenAPI-generated client.
 */
import type {
  BurndownPoint,
  CumulativeFlowPoint,
  EffortLog,
  KpiSnapshot,
  LeadCyclePoint,
  Person,
  Sprint,
  SprintReportRow,
  ThroughputPoint,
  VelocityPoint,
  WorkItem,
} from "./types";

/* ── Helpers ─────────────────────────────────── */
const uid = (i: number) => `00000000-0000-0000-0000-${String(i).padStart(12, "0")}`;
const today = new Date();
const daysAgo = (n: number) => {
  const d = new Date(today);
  d.setDate(d.getDate() - n);
  return d.toISOString().split("T")[0];
};

/* ── People ──────────────────────────────────── */
export const MOCK_PEOPLE: Person[] = [
  { id: uid(1), display_name: "Alice Chen", email: "alice@co.dev", role: "manager", team: "Platform", source_ids: { jira: "ac1" }, created_at: daysAgo(90), updated_at: daysAgo(1) },
  { id: uid(2), display_name: "Bob Müller", email: "bob@co.dev", role: "member", team: "Platform", source_ids: { jira: "bm2" }, created_at: daysAgo(90), updated_at: daysAgo(2) },
  { id: uid(3), display_name: "Carol Reyes", email: "carol@co.dev", role: "member", team: "Mobile", source_ids: { gitlab: 3 }, created_at: daysAgo(60), updated_at: daysAgo(1) },
  { id: uid(4), display_name: "Dan Olsen", email: "dan@co.dev", role: "member", team: "Mobile", source_ids: { gitlab: 4 }, created_at: daysAgo(60), updated_at: daysAgo(3) },
  { id: uid(5), display_name: "Eve Nakamura", email: "eve@co.dev", role: "admin", team: "Platform", source_ids: { jira: "en5" }, created_at: daysAgo(120), updated_at: daysAgo(0) },
];

/* ── Sprints ─────────────────────────────────── */
export const MOCK_SPRINTS: Sprint[] = [
  { id: uid(100), name: "Sprint 22", source: "jira", source_id: "22", board_or_project: "PLAT", status: "closed", start_date: daysAgo(28), end_date: daysAgo(15), goal: "Auth v2 shipped", created_at: daysAgo(30), updated_at: daysAgo(15) },
  { id: uid(101), name: "Sprint 23", source: "jira", source_id: "23", board_or_project: "PLAT", status: "active", start_date: daysAgo(14), end_date: daysAgo(-1), goal: "Dashboard MVP", created_at: daysAgo(16), updated_at: daysAgo(0) },
  { id: uid(102), name: "Sprint 24", source: "jira", source_id: "24", board_or_project: "PLAT", status: "future", start_date: daysAgo(-2), end_date: daysAgo(-16), goal: null, created_at: daysAgo(5), updated_at: daysAgo(5) },
];

/* ── Work Items ──────────────────────────────── */
const statuses: WorkItem["status"][] = ["open", "in_progress", "review", "done", "closed"];
const types: WorkItem["item_type"][] = ["story", "task", "bug", "subtask"];
const priorities: WorkItem["priority"][] = ["critical", "high", "medium", "low"];

export const MOCK_WORK_ITEMS: WorkItem[] = Array.from({ length: 40 }, (_, i) => {
  const status = statuses[i % statuses.length];
  const isDone = status === "done" || status === "closed";
  const sprint = i < 15 ? MOCK_SPRINTS[0] : i < 30 ? MOCK_SPRINTS[1] : MOCK_SPRINTS[2];
  const assignee = MOCK_PEOPLE[i % MOCK_PEOPLE.length];
  return {
    id: uid(200 + i),
    source: i % 3 === 0 ? "gitlab" : "jira",
    source_id: `PLAT-${100 + i}`,
    title: [
      "Implement login page", "Fix auth redirect", "Add logout button",
      "Refactor API client", "Set up CI pipeline", "Update dependencies",
      "Add unit tests", "Create burndown chart", "Build filter bar",
      "Design sprint view", "Add PDF export", "Setup Tailwind",
      "Create KPI cards", "Wire up WebSocket", "Optimize query",
      "Migrate database", "Add error boundary", "Cache API calls",
      "Implement RBAC UI", "Add dark mode", "Fix memory leak",
      "Create Storybook", "Add E2E tests", "Redesign sidebar",
      "Improve a11y", "Paginate work items", "Add search", "Export CSV",
      "Setup monitoring", "Add rate limiting", "Fix CORS", "Add SSO",
      "Create onboarding", "Refactor models", "Add notifications",
      "Fix timezone bug", "Optimize bundle", "Add lazy loading",
      "Create API docs", "Update README",
    ][i],
    description: null,
    item_type: types[i % types.length],
    status,
    priority: priorities[i % priorities.length],
    story_points: [1, 2, 3, 5, 8, 3, 2, 5, 3, 1][i % 10],
    due_date: isDone ? daysAgo(i % 14 + 1) : i % 3 === 0 ? daysAgo(-(i % 7)) : null,
    resolved_at: isDone ? `${daysAgo(i % 10)}T12:00:00Z` : null,
    assignee_id: assignee.id,
    sprint_id: sprint.id,
    parent_id: null,
    labels: i % 4 === 0 ? ["customer:acme"] : i % 5 === 0 ? ["tech-debt"] : [],
    changelog: [
      { field: "status", from: "open", to: status, at: `${daysAgo(i % 10)}T10:00:00Z` },
    ],
    created_at: `${daysAgo(20 + (i % 10))}T09:00:00Z`,
    updated_at: `${daysAgo(i % 5)}T14:00:00Z`,
    assignee,
    sprint,
  };
});

/* ── Effort Logs ─────────────────────────────── */
const categories: EffortLog["category"][] = ["development", "review", "meeting", "support", "admin", "other"];
export const MOCK_EFFORT_LOGS: EffortLog[] = [];
for (let d = 0; d < 14; d++) {
  for (const person of MOCK_PEOPLE) {
    if (d % 7 >= 5) continue; // skip weekends
    MOCK_EFFORT_LOGS.push({
      id: uid(500 + d * 10 + MOCK_PEOPLE.indexOf(person)),
      person_id: person.id,
      day: daysAgo(d),
      hours: 5 + Math.round(Math.random() * 30) / 10,
      category: categories[(d + MOCK_PEOPLE.indexOf(person)) % categories.length],
      description: null,
      work_item_id: MOCK_WORK_ITEMS[(d + MOCK_PEOPLE.indexOf(person)) % MOCK_WORK_ITEMS.length].id,
      source: "manual",
      created_at: `${daysAgo(d)}T18:00:00Z`,
      person,
    });
  }
}

/* ── KPIs ────────────────────────────────────── */
export const MOCK_KPIS: KpiSnapshot[] = [
  { label: "Delivered", value: 18, previousValue: 14, unit: "items", trend: "up", trendIsPositive: true },
  { label: "In Progress", value: 7, previousValue: 9, unit: "items", trend: "down", trendIsPositive: true },
  { label: "Overdue", value: 3, previousValue: 2, unit: "items", trend: "up", trendIsPositive: false },
  { label: "Due Soon", value: 5, previousValue: 4, unit: "items", trend: "up", trendIsPositive: false },
  { label: "Avg Lead Time", value: 6.2, previousValue: 7.1, unit: "days", trend: "down", trendIsPositive: true },
  { label: "Avg Cycle Time", value: 3.4, previousValue: 3.8, unit: "days", trend: "down", trendIsPositive: true },
];

/* ── Burndown ────────────────────────────────── */
export const MOCK_BURNDOWN: BurndownPoint[] = Array.from({ length: 14 }, (_, i) => ({
  date: daysAgo(13 - i),
  ideal: Math.round(40 - (40 / 13) * i),
  actual: Math.max(0, 40 - Math.round((40 / 13) * i * (0.7 + Math.random() * 0.5))),
}));

/* ── Velocity ────────────────────────────────── */
export const MOCK_VELOCITY: VelocityPoint[] = [
  { sprint: "Sprint 18", committed: 30, completed: 26 },
  { sprint: "Sprint 19", committed: 35, completed: 32 },
  { sprint: "Sprint 20", committed: 28, completed: 28 },
  { sprint: "Sprint 21", committed: 32, completed: 24 },
  { sprint: "Sprint 22", committed: 36, completed: 34 },
  { sprint: "Sprint 23", committed: 40, completed: 18 },
];

/* ── Cumulative Flow ─────────────────────────── */
export const MOCK_CUMULATIVE_FLOW: CumulativeFlowPoint[] = Array.from({ length: 30 }, (_, i) => {
  const done = Math.min(40, Math.round(i * 1.3));
  const review = Math.round(Math.max(0, 3 + Math.sin(i / 3) * 2));
  const inProg = Math.round(Math.max(0, 5 + Math.cos(i / 4) * 3));
  return {
    date: daysAgo(29 - i),
    open: Math.max(0, 40 - done - review - inProg),
    in_progress: inProg,
    review,
    done,
  };
});

/* ── Throughput ───────────────────────────────── */
export const MOCK_THROUGHPUT: ThroughputPoint[] = Array.from({ length: 12 }, (_, i) => ({
  week: `W${i + 1}`,
  count: 3 + Math.round(Math.random() * 7),
}));

/* ── Lead / Cycle Time ───────────────────────── */
export const MOCK_LEAD_CYCLE: LeadCyclePoint[] = Array.from({ length: 12 }, (_, i) => ({
  date: daysAgo(84 - i * 7),
  lead_time_days: 5 + Math.round(Math.random() * 40) / 10,
  cycle_time_days: 2 + Math.round(Math.random() * 30) / 10,
}));

/* ── Sprint Report Rows ──────────────────────── */
export const MOCK_SPRINT_REPORT: SprintReportRow[] = MOCK_WORK_ITEMS
  .filter((w) => w.sprint_id === MOCK_SPRINTS[1].id)
  .map((item, i) => ({
    item,
    category: item.status === "done" || item.status === "closed"
      ? "done" as const
      : i > 10
        ? "added_mid_sprint" as const
        : "not_done" as const,
  }));
