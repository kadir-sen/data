"use client";

import { useFilters } from "@/hooks/use-filters";
import { MOCK_PEOPLE, MOCK_SPRINTS } from "@/lib/mock-data";
import { ArrowDownTrayIcon } from "@heroicons/react/24/outline";

export function GlobalFilterBar() {
  const { filters, setFilters } = useFilters();

  const teams = [...new Set(MOCK_PEOPLE.map((p) => p.team).filter(Boolean))] as string[];
  const projects = [
    ...new Set(MOCK_SPRINTS.map((s) => s.board_or_project).filter(Boolean)),
  ] as string[];
  const sprints = MOCK_SPRINTS;

  return (
    <div className="filter-bar no-print flex flex-wrap items-center gap-3 border-b border-gray-200 bg-white px-4 py-2 print:hidden">
      {/* Date range */}
      <label className="flex items-center gap-1 text-xs text-gray-500">
        From
        <input
          type="date"
          value={filters.dateRange.start}
          onChange={(e) =>
            setFilters({
              ...filters,
              dateRange: { ...filters.dateRange, start: e.target.value },
            })
          }
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </label>
      <label className="flex items-center gap-1 text-xs text-gray-500">
        To
        <input
          type="date"
          value={filters.dateRange.end}
          onChange={(e) =>
            setFilters({
              ...filters,
              dateRange: { ...filters.dateRange, end: e.target.value },
            })
          }
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </label>

      {/* Team */}
      <select
        value={filters.team ?? ""}
        onChange={(e) =>
          setFilters({ ...filters, team: e.target.value || null })
        }
        className="rounded border border-gray-300 px-2 py-1 text-sm"
      >
        <option value="">All teams</option>
        {teams.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>

      {/* Project */}
      <select
        value={filters.project ?? ""}
        onChange={(e) =>
          setFilters({ ...filters, project: e.target.value || null })
        }
        className="rounded border border-gray-300 px-2 py-1 text-sm"
      >
        <option value="">All projects</option>
        {projects.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>

      {/* Sprint */}
      <select
        value={filters.sprint ?? ""}
        onChange={(e) =>
          setFilters({ ...filters, sprint: e.target.value || null })
        }
        className="rounded border border-gray-300 px-2 py-1 text-sm"
      >
        <option value="">All sprints</option>
        {sprints.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>

      <div className="ml-auto">
        <button
          onClick={() => window.print()}
          className="flex items-center gap-1 rounded bg-gray-100 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-200"
        >
          <ArrowDownTrayIcon className="h-4 w-4" />
          Export PDF
        </button>
      </div>
    </div>
  );
}
