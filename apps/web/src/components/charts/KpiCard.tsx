"use client";

import clsx from "clsx";
import { ArrowTrendingUpIcon, ArrowTrendingDownIcon, MinusIcon } from "@heroicons/react/24/solid";
import type { KpiSnapshot } from "@/lib/types";

interface KpiCardProps {
  kpi: KpiSnapshot;
  onClick?: () => void;
}

export function KpiCard({ kpi, onClick }: KpiCardProps) {
  const TrendIcon =
    kpi.trend === "up"
      ? ArrowTrendingUpIcon
      : kpi.trend === "down"
        ? ArrowTrendingDownIcon
        : MinusIcon;

  const delta =
    kpi.previousValue != null && typeof kpi.value === "number" && typeof kpi.previousValue === "number"
      ? kpi.value - kpi.previousValue
      : null;

  return (
    <button
      onClick={onClick}
      className={clsx(
        "kpi-card flex flex-col rounded-lg border border-gray-200 bg-white p-4 text-left transition-shadow hover:shadow-md",
        onClick && "cursor-pointer",
      )}
    >
      <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {kpi.label}
      </span>
      <span className="mt-1 text-2xl font-bold text-gray-900">
        {typeof kpi.value === "number" ? kpi.value.toLocaleString() : kpi.value}
        {kpi.unit && <span className="ml-1 text-sm font-normal text-gray-400">{kpi.unit}</span>}
      </span>
      {delta != null && (
        <span
          className={clsx(
            "mt-1 flex items-center gap-1 text-xs font-medium",
            kpi.trendIsPositive ? "text-green-600" : "text-red-500",
          )}
        >
          <TrendIcon className="h-3.5 w-3.5" />
          {delta > 0 ? "+" : ""}
          {delta} since yesterday
        </span>
      )}
    </button>
  );
}
