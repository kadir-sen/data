"use client";

import { useState } from "react";
import { useFilters } from "@/hooks/use-filters";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { CumulativeFlowChart } from "@/components/charts/CumulativeFlowChart";
import { ThroughputChart } from "@/components/charts/ThroughputChart";
import { ChartCard } from "@/components/charts/ChartCard";
import { DrillDownPanel } from "@/components/DrillDownPanel";
import { LoadingState } from "@/components/LoadingState";
import { ErrorState } from "@/components/ErrorState";
import type { WorkItem } from "@/lib/types";

export default function FlowPage() {
  const { filters } = useFilters();
  const { data, loading, error, refetch } = useDashboardData(filters);
  const [drillDown, setDrillDown] = useState<{
    title: string;
    items: WorkItem[];
  } | null>(null);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  return (
    <>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Team Flow</h1>
        <p className="text-sm text-gray-500">
          Cumulative flow and throughput analysis
        </p>
      </div>

      <div className="mb-6">
        <ChartCard title="Cumulative Flow Diagram">
          <CumulativeFlowChart
            data={data.cumulativeFlow}
            onClick={(date) =>
              setDrillDown({
                title: `WIP breakdown on ${date}`,
                items: data.workItems.filter(
                  (w) => w.status !== "done" && w.status !== "closed",
                ),
              })
            }
          />
        </ChartCard>
      </div>

      <ChartCard title="Weekly Throughput">
        <ThroughputChart
          data={data.throughput}
          onClick={(week) =>
            setDrillDown({
              title: `Items completed in ${week}`,
              items: data.workItems.filter(
                (w) => w.status === "done" || w.status === "closed",
              ),
            })
          }
        />
      </ChartCard>

      {/* WIP summary cards */}
      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {(["open", "in_progress", "review", "done"] as const).map((status) => {
          const count = data.workItems.filter((w) => w.status === status).length;
          const label = status.replace("_", " ");
          return (
            <button
              key={status}
              onClick={() =>
                setDrillDown({
                  title: `${label} items`,
                  items: data.workItems.filter((w) => w.status === status),
                })
              }
              className="rounded-lg border border-gray-200 bg-white p-4 text-left hover:shadow-md"
            >
              <p className="text-xs font-medium uppercase text-gray-500">{label}</p>
              <p className="mt-1 text-2xl font-bold text-gray-900">{count}</p>
            </button>
          );
        })}
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
