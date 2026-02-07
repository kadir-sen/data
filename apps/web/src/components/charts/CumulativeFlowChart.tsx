"use client";

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { CumulativeFlowPoint } from "@/lib/types";

interface CumulativeFlowChartProps {
  data: CumulativeFlowPoint[];
  onClick?: (date: string) => void;
}

export function CumulativeFlowChart({ data, onClick }: CumulativeFlowChartProps) {
  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={350}>
        <AreaChart
          data={data}
          onClick={(e) => {
            if (e?.activeLabel && onClick) onClick(e.activeLabel as string);
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Area
            type="monotone"
            dataKey="done"
            stackId="1"
            stroke="#22c55e"
            fill="#bbf7d0"
            name="Done"
          />
          <Area
            type="monotone"
            dataKey="review"
            stackId="1"
            stroke="#eab308"
            fill="#fef08a"
            name="Review"
          />
          <Area
            type="monotone"
            dataKey="in_progress"
            stackId="1"
            stroke="#3b82f6"
            fill="#bfdbfe"
            name="In Progress"
          />
          <Area
            type="monotone"
            dataKey="open"
            stackId="1"
            stroke="#94a3b8"
            fill="#e2e8f0"
            name="Open"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
