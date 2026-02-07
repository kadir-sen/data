"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { VelocityPoint } from "@/lib/types";

interface VelocityChartProps {
  data: VelocityPoint[];
  onClick?: (sprint: string) => void;
}

export function VelocityChart({ data, onClick }: VelocityChartProps) {
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
          <XAxis dataKey="sprint" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Bar dataKey="committed" fill="#c7d2fe" name="Committed" radius={[4, 4, 0, 0]} />
          <Bar dataKey="completed" fill="#6366f1" name="Completed" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
