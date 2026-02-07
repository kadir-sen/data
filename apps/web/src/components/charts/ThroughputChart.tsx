"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type { ThroughputPoint } from "@/lib/types";

interface ThroughputChartProps {
  data: ThroughputPoint[];
  onClick?: (week: string) => void;
}

export function ThroughputChart({ data, onClick }: ThroughputChartProps) {
  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart
          data={data}
          onClick={(e) => {
            if (e?.activeLabel && onClick) onClick(e.activeLabel as string);
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="week" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="count" fill="#6366f1" name="Items completed" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
