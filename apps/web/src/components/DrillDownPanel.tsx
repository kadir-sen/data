"use client";

import { XMarkIcon } from "@heroicons/react/24/outline";
import type { WorkItem } from "@/lib/types";

interface DrillDownPanelProps {
  title: string;
  items: WorkItem[];
  open: boolean;
  onClose: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  open: "bg-gray-100 text-gray-700",
  in_progress: "bg-blue-100 text-blue-700",
  review: "bg-yellow-100 text-yellow-800",
  done: "bg-green-100 text-green-700",
  closed: "bg-gray-200 text-gray-500",
};

export function DrillDownPanel({ title, items, open, onClose }: DrillDownPanelProps) {
  if (!open) return null;

  return (
    <div className="drill-down-panel fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-gray-200 bg-white shadow-lg">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        <button
          onClick={onClose}
          className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        >
          <XMarkIcon className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <p className="p-4 text-sm text-gray-400">No items to display.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {items.map((item) => (
              <li key={item.id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {item.title}
                    </p>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {item.source_id} &middot; {item.item_type} &middot;{" "}
                      {item.assignee?.display_name ?? "Unassigned"}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[item.status] ?? ""}`}
                  >
                    {item.status.replace("_", " ")}
                  </span>
                </div>
                {item.story_points != null && (
                  <p className="mt-1 text-xs text-gray-400">{item.story_points} pts</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-gray-200 px-4 py-2 text-xs text-gray-400">
        {items.length} item{items.length !== 1 ? "s" : ""}
      </div>
    </div>
  );
}
