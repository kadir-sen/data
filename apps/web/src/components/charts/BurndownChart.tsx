"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { BurndownPoint } from "@/lib/types";

interface BurndownChartProps {
  data: BurndownPoint[];
  onClick?: (date: string) => void;
}

export function BurndownChart({ data, onClick }: BurndownChartProps) {
  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart
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
          <Line
            type="monotone"
            dataKey="ideal"
            stroke="#94a3b8"
            strokeDasharray="5 5"
            dot={false}
            name="Ideal"
          />
          <Line
            type="monotone"
            dataKey="actual"
            stroke="#6366f1"
            strokeWidth={2}
            dot={{ r: 3 }}
            name="Actual"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
