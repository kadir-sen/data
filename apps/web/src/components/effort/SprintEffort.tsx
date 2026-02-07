"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CATEGORY_COLORS,
  EFFORT_CATEGORIES,
  type SprintEffortResponse,
} from "@/lib/effort-types";

interface Props {
  token: string;
  sprintId: string;
}

export default function SprintEffort({ token, sprintId }: Props) {
  const [data, setData] = useState<SprintEffortResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/effort/sprint/${sprintId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || `Error ${res.status}`);
        setData(null);
        return;
      }
      setData(await res.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [sprintId, token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div style={containerStyle}>
      <h3 style={{ margin: "0 0 1rem" }}>
        Sprint Effort {data ? `- ${data.sprint_name}` : ""}
      </h3>

      {error && <div style={errorStyle}>{error}</div>}

      {loading ? (
        <p style={{ textAlign: "center", color: "#94a3b8" }}>Loading...</p>
      ) : data ? (
        <>
          {/* Key metrics */}
          <div style={metricsGrid}>
            <MetricCard
              label="Total Effort"
              value={`${data.total_effort_hours.toFixed(1)}h`}
            />
            <MetricCard
              label="Story Points"
              value={
                data.total_story_points != null
                  ? data.total_story_points.toFixed(0)
                  : "N/A"
              }
            />
            <MetricCard
              label="Items Done"
              value={`${data.items_done} / ${data.items_total}`}
            />
            <MetricCard
              label="Completion"
              value={
                data.items_total > 0
                  ? `${Math.round((data.items_done / data.items_total) * 100)}%`
                  : "N/A"
              }
            />
            {data.total_story_points != null &&
              data.total_story_points > 0 && (
                <MetricCard
                  label="Hours/SP"
                  value={(
                    data.total_effort_hours / data.total_story_points
                  ).toFixed(1)}
                />
              )}
          </div>

          {/* Category breakdown */}
          <h4 style={{ margin: "1rem 0 0.5rem", fontSize: "0.9rem" }}>
            Effort by Category
          </h4>
          <div style={barContainer}>
            {EFFORT_CATEGORIES.map((cat) => {
              const val = data.by_category[cat];
              if (!val) return null;
              const pct =
                data.total_effort_hours > 0
                  ? (val / data.total_effort_hours) * 100
                  : 0;
              return (
                <div key={cat} style={catRow}>
                  <span style={catLabel}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        background: CATEGORY_COLORS[cat],
                        display: "inline-block",
                      }}
                    />
                    {cat}
                  </span>
                  <div style={barTrack}>
                    <div
                      style={{
                        width: `${pct}%`,
                        background: CATEGORY_COLORS[cat],
                        height: "100%",
                        borderRadius: 4,
                        minWidth: pct > 0 ? 4 : 0,
                      }}
                    />
                  </div>
                  <span style={{ fontSize: "0.8rem", width: 60, textAlign: "right" }}>
                    {val.toFixed(1)}h ({pct.toFixed(0)}%)
                  </span>
                </div>
              );
            })}
          </div>
        </>
      ) : null}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={cardStyle}>
      <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{label}</div>
      <div style={{ fontSize: "1.25rem", fontWeight: 700 }}>{value}</div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────

const containerStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #e2e8f0",
  borderRadius: 8,
  padding: "1.25rem",
  marginBottom: "1.5rem",
};

const errorStyle: React.CSSProperties = {
  background: "#fef2f2",
  color: "#dc2626",
  padding: "0.5rem 0.75rem",
  borderRadius: 6,
  marginBottom: "0.75rem",
  fontSize: "0.875rem",
};

const metricsGrid: React.CSSProperties = {
  display: "flex",
  gap: "1rem",
  flexWrap: "wrap",
};

const cardStyle: React.CSSProperties = {
  background: "#f8fafc",
  border: "1px solid #e2e8f0",
  borderRadius: 8,
  padding: "0.75rem 1rem",
  minWidth: 110,
  flex: 1,
};

const barContainer: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const catRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
};

const catLabel: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  fontSize: "0.8rem",
  width: 100,
  flexShrink: 0,
};

const barTrack: React.CSSProperties = {
  flex: 1,
  height: 14,
  background: "#f1f5f9",
  borderRadius: 4,
  overflow: "hidden",
};
