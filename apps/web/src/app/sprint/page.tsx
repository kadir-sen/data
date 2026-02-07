"use client";

import { useState } from "react";
import { useFilters } from "@/hooks/use-filters";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { BurndownChart } from "@/components/charts/BurndownChart";
import { VelocityChart } from "@/components/charts/VelocityChart";
import { ChartCard } from "@/components/charts/ChartCard";
import { DataTable } from "@/components/DataTable";
import { DrillDownPanel } from "@/components/DrillDownPanel";
import { LoadingState } from "@/components/LoadingState";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import clsx from "clsx";
import type { SprintReportRow, WorkItem } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  done: "Done",
  not_done: "Not Done",
  added_mid_sprint: "Added Mid-Sprint",
};

const CATEGORY_COLORS: Record<string, string> = {
  done: "bg-green-100 text-green-700",
  not_done: "bg-red-100 text-red-700",
  added_mid_sprint: "bg-yellow-100 text-yellow-800",
};

export default function SprintPage() {
  const { filters } = useFilters();
  const { data, loading, error, refetch } = useDashboardData(filters);
  const [drillDown, setDrillDown] = useState<{
    title: string;
    items: WorkItem[];
  } | null>(null);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  const activeSprint = data.sprints.find((s) => s.status === "active");

  const columns = [
    {
      key: "source_id",
      header: "ID",
      render: (row: SprintReportRow) => (
        <span className="font-mono text-xs text-gray-500">{row.item.source_id}</span>
      ),
      className: "w-24",
    },
    {
      key: "title",
      header: "Title",
      render: (row: SprintReportRow) => (
        <span className="text-sm text-gray-900">{row.item.title}</span>
      ),
    },
    {
      key: "type",
      header: "Type",
      render: (row: SprintReportRow) => (
        <span className="text-xs text-gray-500">{row.item.item_type}</span>
      ),
      className: "w-20",
    },
    {
      key: "points",
      header: "Points",
      render: (row: SprintReportRow) => (
        <span className="text-xs text-gray-600">{row.item.story_points ?? "-"}</span>
      ),
      className: "w-16 text-right",
    },
    {
      key: "assignee",
      header: "Assignee",
      render: (row: SprintReportRow) => (
        <span className="text-xs text-gray-600">
          {row.item.assignee?.display_name ?? "Unassigned"}
        </span>
      ),
      className: "w-28",
    },
    {
      key: "category",
      header: "Category",
      render: (row: SprintReportRow) => (
        <span
          className={clsx(
            "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
            CATEGORY_COLORS[row.category],
          )}
        >
          {CATEGORY_LABELS[row.category]}
        </span>
      ),
      className: "w-32",
    },
  ];

  return (
    <>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Sprint Dashboard</h1>
        {activeSprint && (
          <p className="text-sm text-gray-500">
            {activeSprint.name}
            {activeSprint.goal && ` \u2014 ${activeSprint.goal}`}
            <span className="ml-2 text-xs text-gray-400">
              {activeSprint.start_date} \u2192 {activeSprint.end_date}
            </span>
          </p>
        )}
      </div>

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <ChartCard title="Burndown">
          <BurndownChart
            data={data.burndown}
            onClick={(date) =>
              setDrillDown({
                title: `Items remaining on ${date}`,
                items: data.workItems.filter(
                  (w) => w.status !== "done" && w.status !== "closed",
                ),
              })
            }
          />
        </ChartCard>
        <ChartCard title="Velocity Trend (Last 6 Sprints)">
          <VelocityChart
            data={data.velocity}
            onClick={(sprint) =>
              setDrillDown({
                title: `${sprint} items`,
                items: data.workItems.filter(
                  (w) => w.sprint?.name === sprint,
                ),
              })
            }
          />
        </ChartCard>
      </div>

      {/* Sprint Report Table */}
      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-gray-700">Sprint Report</h3>
        {data.sprintReport.length === 0 ? (
          <EmptyState message="No sprint data available" />
        ) : (
          <DataTable
            columns={columns}
            data={data.sprintReport}
            keyFn={(row) => row.item.id}
            onRowClick={(row) =>
              setDrillDown({ title: row.item.title, items: [row.item] })
            }
          />
        )}
      </section>

      <DrillDownPanel
        title={drillDown?.title ?? ""}
        items={drillDown?.items ?? []}
        open={drillDown !== null}
        onClose={() => setDrillDown(null)}
      />
    </>
  );
}
