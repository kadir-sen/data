"use client";

import { useMemo, useState } from "react";
import { useFilters } from "@/hooks/use-filters";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { DataTable } from "@/components/DataTable";
import { DrillDownPanel } from "@/components/DrillDownPanel";
import { LoadingState } from "@/components/LoadingState";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import clsx from "clsx";
import type { WorkItem } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  open: "bg-gray-100 text-gray-700",
  in_progress: "bg-blue-100 text-blue-700",
  review: "bg-yellow-100 text-yellow-800",
  done: "bg-green-100 text-green-700",
  closed: "bg-gray-200 text-gray-500",
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: "text-red-600",
  high: "text-orange-500",
  medium: "text-yellow-600",
  low: "text-gray-400",
};

export default function ItemsPage() {
  const { filters } = useFilters();
  const { data, loading, error, refetch } = useDashboardData(filters);

  // Local filters
  const [sourceFilter, setSourceFilter] = useState("");
  const [sprintFilter, setSprintFilter] = useState("");
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [labelFilter, setLabelFilter] = useState("");
  const [dueFilter, setDueFilter] = useState<"" | "overdue" | "due_soon" | "no_due">("");

  const [drillDown, setDrillDown] = useState<{
    title: string;
    items: WorkItem[];
  } | null>(null);

  const filtered = useMemo(() => {
    let items = data.workItems;
    if (sourceFilter) items = items.filter((w) => w.source === sourceFilter);
    if (sprintFilter) items = items.filter((w) => w.sprint_id === sprintFilter);
    if (assigneeFilter) items = items.filter((w) => w.assignee_id === assigneeFilter);
    if (labelFilter) items = items.filter((w) => w.labels.some((l) => l.includes(labelFilter)));
    if (dueFilter === "overdue") {
      items = items.filter(
        (w) =>
          w.due_date &&
          new Date(w.due_date) < new Date() &&
          w.status !== "done" &&
          w.status !== "closed",
      );
    } else if (dueFilter === "due_soon") {
      const soon = new Date();
      soon.setDate(soon.getDate() + 3);
      items = items.filter(
        (w) =>
          w.due_date &&
          new Date(w.due_date) <= soon &&
          new Date(w.due_date) >= new Date() &&
          w.status !== "done" &&
          w.status !== "closed",
      );
    } else if (dueFilter === "no_due") {
      items = items.filter((w) => !w.due_date);
    }
    return items;
  }, [data.workItems, sourceFilter, sprintFilter, assigneeFilter, labelFilter, dueFilter]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  const sources = [...new Set(data.workItems.map((w) => w.source))];
  const labels = [...new Set(data.workItems.flatMap((w) => w.labels))].filter(Boolean);

  const columns = [
    {
      key: "source_id",
      header: "ID",
      render: (w: WorkItem) => (
        <span className="font-mono text-xs text-gray-500">{w.source_id}</span>
      ),
      className: "w-24",
    },
    {
      key: "title",
      header: "Title",
      render: (w: WorkItem) => (
        <div>
          <p className="text-sm text-gray-900">{w.title}</p>
          {w.labels.length > 0 && (
            <div className="mt-0.5 flex gap-1">
              {w.labels.map((l) => (
                <span
                  key={l}
                  className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-600"
                >
                  {l}
                </span>
              ))}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "type",
      header: "Type",
      render: (w: WorkItem) => <span className="text-xs text-gray-500">{w.item_type}</span>,
      className: "w-20",
    },
    {
      key: "status",
      header: "Status",
      render: (w: WorkItem) => (
        <span
          className={clsx(
            "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
            STATUS_COLORS[w.status],
          )}
        >
          {w.status.replace("_", " ")}
        </span>
      ),
      className: "w-28",
    },
    {
      key: "priority",
      header: "Priority",
      render: (w: WorkItem) => (
        <span className={clsx("text-xs font-medium", PRIORITY_COLORS[w.priority ?? ""])}>
          {w.priority ?? "-"}
        </span>
      ),
      className: "w-20",
    },
    {
      key: "points",
      header: "Pts",
      render: (w: WorkItem) => (
        <span className="text-xs text-gray-600">{w.story_points ?? "-"}</span>
      ),
      className: "w-12 text-right",
    },
    {
      key: "assignee",
      header: "Assignee",
      render: (w: WorkItem) => (
        <span className="text-xs text-gray-600">
          {w.assignee?.display_name ?? "\u2014"}
        </span>
      ),
      className: "w-28",
    },
    {
      key: "due",
      header: "Due",
      render: (w: WorkItem) => {
        if (!w.due_date) return <span className="text-xs text-gray-300">{"\u2014"}</span>;
        const overdue =
          new Date(w.due_date) < new Date() &&
          w.status !== "done" &&
          w.status !== "closed";
        return (
          <span
            className={clsx(
              "text-xs",
              overdue ? "font-medium text-red-600" : "text-gray-500",
            )}
          >
            {w.due_date}
          </span>
        );
      },
      className: "w-24",
    },
    {
      key: "sprint",
      header: "Sprint",
      render: (w: WorkItem) => (
        <span className="text-xs text-gray-500">
          {w.sprint?.name ?? "\u2014"}
        </span>
      ),
      className: "w-24",
    },
  ];

  return (
    <>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Work Items</h1>
        <p className="text-sm text-gray-500">
          {filtered.length} of {data.workItems.length} items
        </p>
      </div>

      {/* Filters */}
      <div className="no-print mb-4 flex flex-wrap gap-3">
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">All sources</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={sprintFilter}
          onChange={(e) => setSprintFilter(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">All sprints</option>
          {data.sprints.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <select
          value={assigneeFilter}
          onChange={(e) => setAssigneeFilter(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">All assignees</option>
          {data.people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.display_name}
            </option>
          ))}
        </select>
        <select
          value={labelFilter}
          onChange={(e) => setLabelFilter(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">All labels</option>
          {labels.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <select
          value={dueFilter}
          onChange={(e) => setDueFilter(e.target.value as typeof dueFilter)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">All due dates</option>
          <option value="overdue">Overdue</option>
          <option value="due_soon">Due within 3 days</option>
          <option value="no_due">No due date</option>
        </select>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        {filtered.length === 0 ? (
          <EmptyState message="No items match the selected filters" />
        ) : (
          <DataTable
            columns={columns}
            data={filtered}
            keyFn={(w) => w.id}
            onRowClick={(w) => setDrillDown({ title: w.title, items: [w] })}
          />
        )}
      </div>

      <DrillDownPanel
        title={drillDown?.title ?? ""}
        items={drillDown?.items ?? []}
        open={drillDown !== null}
        onClose={() => setDrillDown(null)}
      />
    </>
  );
}
