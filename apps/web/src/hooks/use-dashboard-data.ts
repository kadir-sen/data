"use client";

import { useCallback, useEffect, useState } from "react";
import type { DashboardFilters } from "@/lib/types";
import {
  MOCK_BURNDOWN,
  MOCK_CUMULATIVE_FLOW,
  MOCK_EFFORT_LOGS,
  MOCK_KPIS,
  MOCK_LEAD_CYCLE,
  MOCK_PEOPLE,
  MOCK_SPRINT_REPORT,
  MOCK_SPRINTS,
  MOCK_THROUGHPUT,
  MOCK_VELOCITY,
  MOCK_WORK_ITEMS,
} from "@/lib/mock-data";

/**
 * Hook returning dashboard data.
 * Currently backed by mock data; swap to OpenAPI client calls when ready.
 *
 * Usage pattern:
 *   const { data, loading, error, refetch } = useDashboardData(filters);
 */
export function useDashboardData(_filters: DashboardFilters) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [data, setData] = useState({
    kpis: MOCK_KPIS,
    burndown: MOCK_BURNDOWN,
    velocity: MOCK_VELOCITY,
    cumulativeFlow: MOCK_CUMULATIVE_FLOW,
    throughput: MOCK_THROUGHPUT,
    leadCycle: MOCK_LEAD_CYCLE,
    workItems: MOCK_WORK_ITEMS,
    sprints: MOCK_SPRINTS,
    sprintReport: MOCK_SPRINT_REPORT,
    people: MOCK_PEOPLE,
    effortLogs: MOCK_EFFORT_LOGS,
  });

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    // Simulate async fetch
    const timer = setTimeout(() => {
      setData({
        kpis: MOCK_KPIS,
        burndown: MOCK_BURNDOWN,
        velocity: MOCK_VELOCITY,
        cumulativeFlow: MOCK_CUMULATIVE_FLOW,
        throughput: MOCK_THROUGHPUT,
        leadCycle: MOCK_LEAD_CYCLE,
        workItems: MOCK_WORK_ITEMS,
        sprints: MOCK_SPRINTS,
        sprintReport: MOCK_SPRINT_REPORT,
        people: MOCK_PEOPLE,
        effortLogs: MOCK_EFFORT_LOGS,
      });
      setLoading(false);
    }, 400);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const cleanup = refetch();
    return cleanup;
  }, [refetch]);

  return { data, loading, error, refetch };
}
