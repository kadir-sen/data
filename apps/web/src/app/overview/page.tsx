"use client";

import { useState } from "react";
import { useFilters } from "@/hooks/use-filters";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { KpiCard } from "@/components/charts/KpiCard";
import { LeadCycleTimeChart } from "@/components/charts/LeadCycleTimeChart";
import { ChartCard } from "@/components/charts/ChartCard";
import { DrillDownPanel } from "@/components/DrillDownPanel";
import { LoadingState } from "@/components/LoadingState";
import { ErrorState } from "@/components/ErrorState";
import type { WorkItem } from "@/lib/types";

export default function OverviewPage() {
  const { filters } = useFilters();
  const { data, loading, error, refetch } = useDashboardData(filters);
  const [drillDown, setDrillDown] = useState<{
    title: string;
    items: WorkItem[];
  } | null>(null);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  const kpiItemMap: Record<string, (items: WorkItem[]) => WorkItem[]> = {
    Delivered: (items) => items.filter((w) => w.status === "done" || w.status === "closed"),
    "In Progress": (items) => items.filter((w) => w.status === "in_progress"),
    Overdue: (items) =>
      items.filter(
        (w) =>
          w.due_date &&
          new Date(w.due_date) < new Date() &&
          w.status !== "done" &&
          w.status !== "closed",
      ),
    "Due Soon": (items) => {
      const soon = new Date();
      soon.setDate(soon.getDate() + 3);
      return items.filter(
        (w) =>
          w.due_date &&
          new Date(w.due_date) <= soon &&
          new Date(w.due_date) >= new Date() &&
          w.status !== "done" &&
          w.status !== "closed",
      );
    },
  };

  return (
    <>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Executive Overview</h1>
        <p className="text-sm text-gray-500">
          Key metrics and what changed since yesterday
        </p>
      </div>

      {/* KPI grid */}
      <div className="kpi-grid mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {data.kpis.map((kpi) => (
          <KpiCard
            key={kpi.label}
            kpi={kpi}
            onClick={
              kpiItemMap[kpi.label]
                ? () =>
                    setDrillDown({
                      title: kpi.label,
                      items: kpiItemMap[kpi.label](data.workItems),
                    })
                : undefined
            }
          />
        ))}
      </div>

      {/* Lead / Cycle time trend */}
      <ChartCard title="Lead Time & Cycle Time Trend">
        <LeadCycleTimeChart data={data.leadCycle} />
      </ChartCard>

      {/* What changed since yesterday */}
      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-gray-700">
          What Changed Since Yesterday
        </h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <DeltaCard label="Newly done" count={4} color="green" />
          <DeltaCard label="Moved to In Progress" count={2} color="blue" />
          <DeltaCard label="Became overdue" count={1} color="red" />
        </div>
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

function DeltaCard({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: "green" | "blue" | "red";
}) {
  const bg = { green: "bg-green-50", blue: "bg-blue-50", red: "bg-red-50" }[color];
  const text = { green: "text-green-700", blue: "text-blue-700", red: "text-red-700" }[color];
  const badge = { green: "bg-green-100", blue: "bg-blue-100", red: "bg-red-100" }[color];

  return (
    <div className={`rounded-lg ${bg} p-3`}>
      <span className={`text-xs font-medium ${text}`}>{label}</span>
      <span className={`ml-2 inline-flex items-center rounded-full ${badge} px-2 py-0.5 text-xs font-bold ${text}`}>
        +{count}
      </span>
    </div>
  );
}
