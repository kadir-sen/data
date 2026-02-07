"use client";

import { useMemo, useState } from "react";
import { useFilters } from "@/hooks/use-filters";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { DataTable } from "@/components/DataTable";
import { ChartCard } from "@/components/charts/ChartCard";
import { LoadingState } from "@/components/LoadingState";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { EffortLog } from "@/lib/types";

type ViewMode = "my" | "team" | "sprint";

const CATEGORY_COLORS: Record<string, string> = {
  development: "#6366f1",
  review: "#f59e0b",
  meeting: "#ef4444",
  support: "#22c55e",
  admin: "#94a3b8",
  other: "#d1d5db",
};

export default function EffortPage() {
  const { filters } = useFilters();
  const { data, loading, error, refetch } = useDashboardData(filters);
  const [view, setView] = useState<ViewMode>("team");
  const [selectedPerson, setSelectedPerson] = useState("");

  const logs = useMemo(() => {
    let result = data.effortLogs;
    if (view === "my" || selectedPerson) {
      const personId = selectedPerson || data.people[0]?.id;
      result = result.filter((l) => l.person_id === personId);
    }
    return result;
  }, [data.effortLogs, data.people, view, selectedPerson]);

  // Aggregate by day for chart
  const dailyByCategory = useMemo(() => {
    const map = new Map<string, Record<string, number>>();
    for (const log of logs) {
      const existing = map.get(log.day) ?? {};
      existing[log.category] = (existing[log.category] ?? 0) + log.hours;
      map.set(log.day, existing);
    }
    return [...map.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, cats]) => ({ day, ...cats }));
  }, [logs]);

  // Aggregate totals per person
  const personTotals = useMemo(() => {
    const map = new Map<string, { name: string; hours: number }>();
    for (const log of data.effortLogs) {
      const existing = map.get(log.person_id) ?? {
        name: log.person?.display_name ?? "Unknown",
        hours: 0,
      };
      existing.hours += log.hours;
      map.set(log.person_id, existing);
    }
    return [...map.values()].sort((a, b) => b.hours - a.hours);
  }, [data.effortLogs]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  const tableColumns = [
    {
      key: "day",
      header: "Date",
      render: (l: EffortLog) => (
        <span className="text-sm text-gray-900">{l.day}</span>
      ),
      className: "w-24",
    },
    {
      key: "person",
      header: "Person",
      render: (l: EffortLog) => (
        <span className="text-sm text-gray-700">
          {l.person?.display_name ?? "\u2014"}
        </span>
      ),
      className: "w-28",
    },
    {
      key: "hours",
      header: "Hours",
      render: (l: EffortLog) => (
        <span className="text-sm font-medium text-gray-900">
          {l.hours.toFixed(1)}h
        </span>
      ),
      className: "w-16 text-right",
    },
    {
      key: "category",
      header: "Category",
      render: (l: EffortLog) => (
        <span className="inline-flex items-center gap-1 text-xs text-gray-600">
          <span
            className="h-2 w-2 rounded-full"
            style={{
              backgroundColor: CATEGORY_COLORS[l.category] ?? "#d1d5db",
            }}
          />
          {l.category}
        </span>
      ),
      className: "w-28",
    },
    {
      key: "description",
      header: "Notes",
      render: (l: EffortLog) => (
        <span className="text-xs text-gray-400">
          {l.description ?? "\u2014"}
        </span>
      ),
    },
  ];

  const totalHours = logs.reduce((s, l) => s + l.hours, 0);
  const categories = [...new Set(logs.map((l) => l.category))];

  return (
    <>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Effort</h1>
          <p className="text-sm text-gray-500">
            Time tracking &middot; {totalHours.toFixed(1)} total hours
          </p>
        </div>

        <div className="no-print flex gap-2">
          {(["my", "team", "sprint"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setView(m)}
              className={`rounded px-3 py-1.5 text-sm font-medium ${
                view === m
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {m === "my" ? "My" : m === "team" ? "Team" : "Sprint"}
            </button>
          ))}
        </div>
      </div>

      {/* Person picker for "my" view */}
      {view === "my" && (
        <div className="no-print mb-4">
          <select
            value={selectedPerson}
            onChange={(e) => setSelectedPerson(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          >
            {data.people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Stacked bar chart: hours by day/category */}
      <ChartCard title="Daily Effort by Category" className="mb-6">
        {dailyByCategory.length === 0 ? (
          <EmptyState message="No effort data for selected period" />
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={dailyByCategory}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} />
              <YAxis unit="h" tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              {categories.map((cat) => (
                <Bar
                  key={cat}
                  dataKey={cat}
                  stackId="effort"
                  fill={CATEGORY_COLORS[cat] ?? "#d1d5db"}
                  name={cat}
                  radius={[2, 2, 0, 0]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      {/* Team summary table (only in team view) */}
      {view === "team" && (
        <section className="mb-6 rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-gray-700">
            Team Summary
          </h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {personTotals.map((p) => (
              <div
                key={p.name}
                className="rounded border border-gray-100 bg-gray-50 p-3"
              >
                <p className="text-xs font-medium text-gray-600">{p.name}</p>
                <p className="text-lg font-bold text-gray-900">
                  {p.hours.toFixed(1)}h
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Detail table */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-gray-700">
          Effort Log
        </h3>
        {logs.length === 0 ? (
          <EmptyState message="No effort entries" />
        ) : (
          <DataTable columns={tableColumns} data={logs} keyFn={(l) => l.id} />
        )}
      </div>
    </>
  );
}
