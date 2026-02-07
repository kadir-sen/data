"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import {
  ChartBarIcon,
  ClipboardDocumentListIcon,
  ClockIcon,
  PresentationChartLineIcon,
  RectangleGroupIcon,
} from "@heroicons/react/24/outline";

const NAV_ITEMS = [
  { href: "/overview", label: "Overview", icon: PresentationChartLineIcon },
  { href: "/sprint", label: "Sprint", icon: ChartBarIcon },
  { href: "/flow", label: "Team Flow", icon: RectangleGroupIcon },
  { href: "/items", label: "Work Items", icon: ClipboardDocumentListIcon },
  { href: "/effort", label: "Effort", icon: ClockIcon },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="no-print flex w-56 shrink-0 flex-col border-r border-gray-200 bg-gray-50 print:hidden">
      <div className="flex h-14 items-center border-b border-gray-200 px-4">
        <span className="text-lg font-bold text-gray-900">Case</span>
        <span className="ml-1 text-xs text-gray-400">analytics</span>
      </div>

      <ul className="mt-2 flex flex-col gap-0.5 px-2">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href === "/overview" && pathname === "/");
          return (
            <li key={href}>
              <Link
                href={href}
                className={clsx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
                )}
              >
                <Icon className="h-5 w-5 shrink-0" />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
