import type { ReactNode } from "react";

interface ChartCardProps {
  title: string;
  children: ReactNode;
  className?: string;
}

export function ChartCard({ title, children, className = "" }: ChartCardProps) {
  return (
    <section
      className={`rounded-lg border border-gray-200 bg-white p-4 ${className}`}
    >
      <h3 className="mb-3 text-sm font-semibold text-gray-700">{title}</h3>
      {children}
    </section>
  );
}
