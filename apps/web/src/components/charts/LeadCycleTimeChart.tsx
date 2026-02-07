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
import type { LeadCyclePoint } from "@/lib/types";

interface LeadCycleTimeChartProps {
  data: LeadCyclePoint[];
}

export function LeadCycleTimeChart({ data }: LeadCycleTimeChartProps) {
  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis unit=" d" tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Line
            type="monotone"
            dataKey="lead_time_days"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={{ r: 3 }}
            name="Lead Time"
          />
          <Line
            type="monotone"
            dataKey="cycle_time_days"
            stroke="#6366f1"
            strokeWidth={2}
            dot={{ r: 3 }}
            name="Cycle Time"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
