"use client";

import { useState, type ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { GlobalFilterBar } from "./GlobalFilterBar";
import { FiltersContext, DEFAULT_FILTERS } from "@/hooks/use-filters";
import type { DashboardFilters } from "@/lib/types";

export function DashboardShell({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS);

  return (
    <FiltersContext.Provider value={{ filters, setFilters }}>
      <div className="dashboard-shell flex h-screen overflow-hidden bg-white">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <GlobalFilterBar />
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
        </div>
      </div>
    </FiltersContext.Provider>
  );
}
