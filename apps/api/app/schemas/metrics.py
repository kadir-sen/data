"""Metrics schemas — chart-ready series + table-ready rows."""

from pydantic import BaseModel, Field


class ChartSeries(BaseModel):
    """A single series for a line/bar chart (e.g. Recharts, Chart.js)."""

    name: str = Field(..., examples=["Velocity"])
    data: list[dict] = Field(
        ...,
        description="Array of {x, y} or {label, value} points",
        examples=[[{"x": "Sprint 40", "y": 35}, {"x": "Sprint 41", "y": 42}]],
    )


class TableRow(BaseModel):
    """Generic key-value row for data tables."""

    values: dict = Field(
        ...,
        examples=[{"sprint": "Sprint 42", "velocity": 42, "done": 12, "total": 18}],
    )


class VelocityPoint(BaseModel):
    sprint_name: str
    committed: float
    completed: float


class BurndownPoint(BaseModel):
    day: str = Field(..., description="ISO date string")
    ideal: float
    actual: float


class ScopeChange(BaseModel):
    added: int
    removed: int
    added_points: float
    removed_points: float
    net_points: float


class SprintReportItem(BaseModel):
    source_id: str
    title: str
    story_points: float
    status: str


class SprintReport(BaseModel):
    done: list[SprintReportItem]
    not_done: list[SprintReportItem]


class LeadCycleTime(BaseModel):
    lead_time_median_days: float | None
    lead_time_count: int
    cycle_time_median_days: float | None
    cycle_time_count: int


class ThroughputDay(BaseModel):
    date: str
    count: int


class ThroughputWeek(BaseModel):
    week: str
    count: int


class Throughput(BaseModel):
    daily: list[ThroughputDay]
    weekly: list[ThroughputWeek]
    total: int


class DueDateRiskItem(BaseModel):
    source_id: str
    title: str
    due_date: str | None
    status: str
    labels: list[str]


class DueDateRisk(BaseModel):
    overdue: list[DueDateRiskItem]
    due_7d: list[DueDateRiskItem]
    due_14d: list[DueDateRiskItem]
    no_due_date: list[DueDateRiskItem]
    by_label: dict[str, dict[str, int]]


class SprintInfo(BaseModel):
    id: str
    name: str
    status: str
    start_date: str
    end_date: str


class SprintBurndownSeries(BaseModel):
    date: str
    remaining: float
    completed: float


class SprintMetricsResponse(BaseModel):
    """Full sprint dashboard metrics."""

    sprint: SprintInfo
    burndown: list[SprintBurndownSeries]
    velocity: VelocityPoint
    scope_change: ScopeChange
    report: SprintReport
    cumulative_flow: list[dict]
    lead_cycle_time: LeadCycleTime
    throughput: Throughput


class TeamMetricsResponse(BaseModel):
    """Team dashboard metrics over a date range."""

    team_id: str
    from_date: str = Field(..., alias="from")
    to_date: str = Field(..., alias="to")
    velocity: list[VelocityPoint]
    cumulative_flow: list[dict]
    lead_cycle_time: LeadCycleTime
    throughput: Throughput
    due_date_risk: DueDateRisk

    model_config = {"populate_by_name": True}


class MetricsResponse(BaseModel):
    """Unified metrics endpoint returning both chart-ready and table-ready data."""

    charts: dict[str, list[ChartSeries]] = Field(
        default_factory=dict,
        description="Chart-ready series keyed by metric name",
        examples=[{
            "velocity": [{"name": "Committed", "data": [{"x": "Sprint 41", "y": 40}]}],
        }],
    )
    tables: dict[str, list[TableRow]] = Field(
        default_factory=dict,
        description="Table-ready rows keyed by metric name",
    )
    summary: dict = Field(
        default_factory=dict,
        description="Top-level KPI values for dashboard cards",
        examples=[{"velocity_avg": 38.5, "burndown_remaining": 12, "total_effort_hours": 640}],
    )
