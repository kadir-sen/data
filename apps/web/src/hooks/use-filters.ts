"use client";

import { createContext, useContext } from "react";
import type { DashboardFilters } from "@/lib/types";

const today = new Date();
const thirtyDaysAgo = new Date(today);
thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

export const DEFAULT_FILTERS: DashboardFilters = {
  dateRange: {
    start: thirtyDaysAgo.toISOString().split("T")[0],
    end: today.toISOString().split("T")[0],
  },
  team: null,
  project: null,
  sprint: null,
};

export const FiltersContext = createContext<{
  filters: DashboardFilters;
  setFilters: (f: DashboardFilters) => void;
}>({
  filters: DEFAULT_FILTERS,
  setFilters: () => {},
});

export function useFilters() {
  return useContext(FiltersContext);
}
