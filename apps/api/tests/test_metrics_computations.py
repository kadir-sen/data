"""Golden-dataset tests for agile metrics computations.

Each test builds a deterministic dataset (no database required) and verifies
the computation output against hand-calculated expected values.
"""

from datetime import date, datetime

import pytest

from app.services.metrics import (
    compute_burndown,
    compute_cumulative_flow,
    compute_due_date_risk,
    compute_lead_cycle_times,
    compute_scope_change,
    compute_sprint_report,
    compute_throughput,
    compute_velocity,
)

# ═══════════════════════════════════════════════════════════════════
# Golden dataset fixtures
# ═══════════════════════════════════════════════════════════════════

SPRINT_START = date(2025, 1, 6)
SPRINT_END = date(2025, 1, 10)  # Mon–Fri, 5 days


def _make_item(
    *,
    source_id: str = "PROJ-1",
    title: str = "Task",
    story_points: float = 0,
    status: str = "open",
    created_at: str = "2025-01-05T09:00:00+00:00",
    resolved_at: str | None = None,
    due_date: str | None = None,
    labels: list[str] | None = None,
    changelog: list[dict] | None = None,
) -> dict:
    return {
        "source_id": source_id,
        "title": title,
        "story_points": story_points,
        "status": status,
        "created_at": created_at,
        "resolved_at": resolved_at,
        "due_date": due_date,
        "labels": labels or [],
        "changelog": changelog or [],
    }


# Five items, total 20 story points, staggered completions
GOLDEN_ITEMS = [
    _make_item(
        source_id="PROJ-1",
        title="Auth login",
        story_points=5,
        status="done",
        resolved_at="2025-01-07T16:00:00+00:00",
        changelog=[
            {"field": "status", "from": "open", "to": "in_progress", "at": "2025-01-06T10:00:00+00:00"},
            {"field": "status", "from": "in_progress", "to": "done", "at": "2025-01-07T16:00:00+00:00"},
        ],
    ),
    _make_item(
        source_id="PROJ-2",
        title="Auth logout",
        story_points=3,
        status="done",
        resolved_at="2025-01-08T11:00:00+00:00",
        changelog=[
            {"field": "status", "from": "open", "to": "in_progress", "at": "2025-01-07T09:00:00+00:00"},
            {"field": "status", "from": "in_progress", "to": "review", "at": "2025-01-08T09:00:00+00:00"},
            {"field": "status", "from": "review", "to": "done", "at": "2025-01-08T11:00:00+00:00"},
        ],
    ),
    _make_item(
        source_id="PROJ-3",
        title="Dashboard UI",
        story_points=8,
        status="done",
        resolved_at="2025-01-10T14:00:00+00:00",
        changelog=[
            {"field": "status", "from": "open", "to": "in_progress", "at": "2025-01-06T14:00:00+00:00"},
            {"field": "status", "from": "in_progress", "to": "done", "at": "2025-01-10T14:00:00+00:00"},
        ],
    ),
    _make_item(
        source_id="PROJ-4",
        title="API docs",
        story_points=2,
        status="in_progress",
        changelog=[
            {"field": "status", "from": "open", "to": "in_progress", "at": "2025-01-09T10:00:00+00:00"},
        ],
    ),
    _make_item(
        source_id="PROJ-5",
        title="Bug fix",
        story_points=2,
        status="open",
    ),
]


# ═══════════════════════════════════════════════════════════════════
# Burndown
# ═══════════════════════════════════════════════════════════════════

class TestBurndown:
    def test_burndown_series_length(self):
        series = compute_burndown(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        # 5 days: Jan 6–10 inclusive
        assert len(series) == 5

    def test_burndown_starts_at_total(self):
        series = compute_burndown(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        # Day 1 (Jan 6): nothing completed yet → remaining = 20
        assert series[0]["remaining"] == 20.0
        assert series[0]["completed"] == 0.0

    def test_burndown_day_2(self):
        series = compute_burndown(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        # Jan 7: PROJ-1 (5 pts) completed
        assert series[1]["remaining"] == 15.0
        assert series[1]["completed"] == 5.0

    def test_burndown_day_3(self):
        series = compute_burndown(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        # Jan 8: PROJ-2 (3 pts) completed → cumulative 8
        assert series[2]["remaining"] == 12.0
        assert series[2]["completed"] == 8.0

    def test_burndown_day_4_no_completion(self):
        series = compute_burndown(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        # Jan 9: no completion → same as day 3
        assert series[3]["remaining"] == 12.0
        assert series[3]["completed"] == 8.0

    def test_burndown_final_day(self):
        series = compute_burndown(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        # Jan 10: PROJ-3 (8 pts) completed → cumulative 16
        assert series[4]["remaining"] == 4.0
        assert series[4]["completed"] == 16.0

    def test_burndown_empty_sprint(self):
        series = compute_burndown([], SPRINT_START, SPRINT_END)
        assert len(series) == 5
        assert all(p["remaining"] == 0.0 for p in series)


# ═══════════════════════════════════════════════════════════════════
# Velocity
# ═══════════════════════════════════════════════════════════════════

class TestVelocity:
    def test_single_sprint(self):
        sprint = {"name": "Sprint 42"}
        result = compute_velocity([(sprint, GOLDEN_ITEMS)])
        assert len(result) == 1
        assert result[0]["sprint_name"] == "Sprint 42"
        # Committed: sum of all story points = 5+3+8+2+2 = 20
        assert result[0]["committed"] == 20.0
        # Completed: only done/closed items = 5+3+8 = 16
        assert result[0]["completed"] == 16.0

    def test_multiple_sprints(self):
        s1 = {"name": "Sprint 1"}
        s2 = {"name": "Sprint 2"}
        items1 = [_make_item(story_points=5, status="done")]
        items2 = [_make_item(story_points=8, status="done"), _make_item(story_points=3, status="open")]
        result = compute_velocity([(s1, items1), (s2, items2)])
        assert len(result) == 2
        assert result[0]["committed"] == 5.0
        assert result[0]["completed"] == 5.0
        assert result[1]["committed"] == 11.0
        assert result[1]["completed"] == 8.0

    def test_zero_points(self):
        sprint = {"name": "Empty"}
        result = compute_velocity([(sprint, [])])
        assert result[0]["committed"] == 0.0
        assert result[0]["completed"] == 0.0


# ═══════════════════════════════════════════════════════════════════
# Scope change
# ═══════════════════════════════════════════════════════════════════

class TestScopeChange:
    def test_item_added_after_start(self):
        items = [
            _make_item(
                source_id="LATE-1",
                story_points=3,
                created_at="2025-01-08T10:00:00+00:00",  # after sprint start
            ),
            _make_item(
                source_id="ORIG-1",
                story_points=5,
                created_at="2025-01-04T10:00:00+00:00",  # before sprint start
            ),
        ]
        result = compute_scope_change(items, SPRINT_START)
        assert result["added"] == 1
        assert result["added_points"] == 3.0

    def test_no_scope_change(self):
        items = [
            _make_item(created_at="2025-01-04T10:00:00+00:00", story_points=5),
        ]
        result = compute_scope_change(items, SPRINT_START)
        assert result["added"] == 0
        assert result["removed"] == 0
        assert result["net_points"] == 0.0

    def test_item_removed_via_changelog(self):
        items = [
            _make_item(
                story_points=4,
                created_at="2025-01-04T10:00:00+00:00",
                changelog=[
                    {"field": "sprint", "from": "sprint-a", "to": None, "at": "2025-01-08T10:00:00+00:00"},
                ],
            ),
        ]
        result = compute_scope_change(items, SPRINT_START)
        assert result["removed"] == 1
        assert result["removed_points"] == 4.0


# ═══════════════════════════════════════════════════════════════════
# Sprint report
# ═══════════════════════════════════════════════════════════════════

class TestSprintReport:
    def test_done_vs_not_done(self):
        report = compute_sprint_report(GOLDEN_ITEMS)
        # 3 items done (PROJ-1, PROJ-2, PROJ-3), 2 not done (PROJ-4, PROJ-5)
        assert len(report["done"]) == 3
        assert len(report["not_done"]) == 2

    def test_done_source_ids(self):
        report = compute_sprint_report(GOLDEN_ITEMS)
        done_ids = {i["source_id"] for i in report["done"]}
        assert done_ids == {"PROJ-1", "PROJ-2", "PROJ-3"}

    def test_not_done_source_ids(self):
        report = compute_sprint_report(GOLDEN_ITEMS)
        not_done_ids = {i["source_id"] for i in report["not_done"]}
        assert not_done_ids == {"PROJ-4", "PROJ-5"}

    def test_story_points_preserved(self):
        report = compute_sprint_report(GOLDEN_ITEMS)
        total_done_pts = sum(i["story_points"] for i in report["done"])
        assert total_done_pts == 16.0


# ═══════════════════════════════════════════════════════════════════
# Cumulative flow
# ═══════════════════════════════════════════════════════════════════

class TestCumulativeFlow:
    def test_series_length(self):
        flow = compute_cumulative_flow(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        assert len(flow) == 5

    def test_final_day_counts(self):
        flow = compute_cumulative_flow(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        final = flow[-1]  # Jan 10
        # By Jan 10: PROJ-1=done, PROJ-2=done, PROJ-3=done, PROJ-4=in_progress, PROJ-5=open(todo)
        assert final["done"] == 3
        assert final["in_progress"] == 1
        assert final["todo"] == 1

    def test_first_day_counts(self):
        flow = compute_cumulative_flow(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        first = flow[0]  # Jan 6
        # On Jan 6: PROJ-1 → in_progress, PROJ-3 → in_progress,
        # PROJ-2/4/5 still at open (created Jan 5, no status change yet on Jan 6 for PROJ-2)
        # Actually PROJ-2 was created Jan 5 at open, transitions on Jan 7.
        # PROJ-4 transitions on Jan 9. PROJ-5 never transitions.
        assert first["done"] == 0
        # PROJ-1 and PROJ-3 moved to in_progress on Jan 6
        assert first["in_progress"] == 2
        # PROJ-2, PROJ-4, PROJ-5 still at todo
        assert first["todo"] == 3


# ═══════════════════════════════════════════════════════════════════
# Lead time / Cycle time
# ═══════════════════════════════════════════════════════════════════

class TestLeadCycleTime:
    def test_lead_time_count(self):
        result = compute_lead_cycle_times(GOLDEN_ITEMS)
        # 3 resolved items (PROJ-1, PROJ-2, PROJ-3)
        assert result["lead_time_count"] == 3

    def test_cycle_time_count(self):
        result = compute_lead_cycle_times(GOLDEN_ITEMS)
        # 3 items have in_progress transitions + resolved_at
        assert result["cycle_time_count"] == 3

    def test_lead_time_values(self):
        result = compute_lead_cycle_times(GOLDEN_ITEMS)
        # PROJ-1: created Jan 5 09:00, resolved Jan 7 16:00 → ~2.29 days
        # PROJ-2: created Jan 5 09:00, resolved Jan 8 11:00 → ~3.08 days
        # PROJ-3: created Jan 5 09:00, resolved Jan 10 14:00 → ~5.21 days
        # Median of [2.29, 3.08, 5.21] = 3.08
        assert result["lead_time_median_days"] is not None
        assert 3.0 <= result["lead_time_median_days"] <= 3.2

    def test_cycle_time_values(self):
        result = compute_lead_cycle_times(GOLDEN_ITEMS)
        # PROJ-1: in_progress Jan 6 10:00, resolved Jan 7 16:00 → 1.25 days
        # PROJ-2: in_progress Jan 7 09:00, resolved Jan 8 11:00 → ~1.08 days
        # PROJ-3: in_progress Jan 6 14:00, resolved Jan 10 14:00 → 4.0 days
        # Median of [1.08, 1.25, 4.0] = 1.25
        assert result["cycle_time_median_days"] is not None
        assert 1.2 <= result["cycle_time_median_days"] <= 1.3

    def test_no_resolved_items(self):
        items = [_make_item(status="open")]
        result = compute_lead_cycle_times(items)
        assert result["lead_time_median_days"] is None
        assert result["cycle_time_median_days"] is None
        assert result["lead_time_count"] == 0


# ═══════════════════════════════════════════════════════════════════
# Throughput
# ═══════════════════════════════════════════════════════════════════

class TestThroughput:
    def test_total(self):
        result = compute_throughput(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        # 3 items completed in range
        assert result["total"] == 3

    def test_daily_series_length(self):
        result = compute_throughput(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        assert len(result["daily"]) == 5

    def test_daily_counts(self):
        result = compute_throughput(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        daily_map = {d["date"]: d["count"] for d in result["daily"]}
        assert daily_map["2025-01-06"] == 0
        assert daily_map["2025-01-07"] == 1  # PROJ-1
        assert daily_map["2025-01-08"] == 1  # PROJ-2
        assert daily_map["2025-01-09"] == 0
        assert daily_map["2025-01-10"] == 1  # PROJ-3

    def test_weekly_aggregation(self):
        result = compute_throughput(GOLDEN_ITEMS, SPRINT_START, SPRINT_END)
        assert len(result["weekly"]) >= 1
        total_weekly = sum(w["count"] for w in result["weekly"])
        assert total_weekly == 3

    def test_empty_range(self):
        result = compute_throughput([], SPRINT_START, SPRINT_END)
        assert result["total"] == 0


# ═══════════════════════════════════════════════════════════════════
# Due-date risk
# ═══════════════════════════════════════════════════════════════════

class TestDueDateRisk:
    def _risk_items(self) -> list[dict]:
        return [
            _make_item(
                source_id="OVERDUE-1",
                title="Overdue task",
                status="open",
                due_date="2025-01-05",
                labels=["customer-acme"],
            ),
            _make_item(
                source_id="DUE7-1",
                title="Due in 3 days",
                status="in_progress",
                due_date="2025-01-13",
                labels=["customer-acme"],
            ),
            _make_item(
                source_id="DUE14-1",
                title="Due in 12 days",
                status="open",
                due_date="2025-01-22",
                labels=["customer-beta"],
            ),
            _make_item(
                source_id="SAFE-1",
                title="Due in 30 days",
                status="open",
                due_date="2025-02-09",
            ),
            _make_item(
                source_id="DONE-1",
                title="Already done",
                status="done",
                due_date="2025-01-05",
            ),
            _make_item(
                source_id="NODUE-1",
                title="No due date",
                status="open",
            ),
        ]

    def test_overdue(self):
        result = compute_due_date_risk(self._risk_items(), as_of=date(2025, 1, 10))
        assert len(result["overdue"]) == 1
        assert result["overdue"][0]["source_id"] == "OVERDUE-1"

    def test_due_7d(self):
        result = compute_due_date_risk(self._risk_items(), as_of=date(2025, 1, 10))
        assert len(result["due_7d"]) == 1
        assert result["due_7d"][0]["source_id"] == "DUE7-1"

    def test_due_14d(self):
        result = compute_due_date_risk(self._risk_items(), as_of=date(2025, 1, 10))
        assert len(result["due_14d"]) == 1
        assert result["due_14d"][0]["source_id"] == "DUE14-1"

    def test_done_items_excluded(self):
        result = compute_due_date_risk(self._risk_items(), as_of=date(2025, 1, 10))
        all_ids = set()
        for bucket in ("overdue", "due_7d", "due_14d", "no_due_date"):
            for item in result[bucket]:
                all_ids.add(item["source_id"])
        assert "DONE-1" not in all_ids

    def test_no_due_date_bucket(self):
        result = compute_due_date_risk(self._risk_items(), as_of=date(2025, 1, 10))
        assert len(result["no_due_date"]) == 1
        assert result["no_due_date"][0]["source_id"] == "NODUE-1"

    def test_by_label_aggregation(self):
        result = compute_due_date_risk(self._risk_items(), as_of=date(2025, 1, 10))
        assert "customer-acme" in result["by_label"]
        acme = result["by_label"]["customer-acme"]
        assert acme["overdue"] == 1
        assert acme["due_7d"] == 1

    def test_safe_items_not_in_risk(self):
        """Items due > 14 days out should not appear in any risk bucket."""
        result = compute_due_date_risk(self._risk_items(), as_of=date(2025, 1, 10))
        all_risk_ids = set()
        for bucket in ("overdue", "due_7d", "due_14d"):
            for item in result[bucket]:
                all_risk_ids.add(item["source_id"])
        assert "SAFE-1" not in all_risk_ids
