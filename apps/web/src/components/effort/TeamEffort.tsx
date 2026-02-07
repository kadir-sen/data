"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CATEGORY_COLORS,
  EFFORT_CATEGORIES,
  type EffortCategory,
  type TeamEffortResponse,
} from "@/lib/effort-types";

interface Props {
  token: string;
  teamId: string;
}

function fmt(d: Date) {
  return d.toISOString().slice(0, 10);
}

export default function TeamEffort({ token, teamId }: Props) {
  const [from, setFrom] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return fmt(d);
  });
  const [to, setTo] = useState(() => fmt(new Date()));
  const [data, setData] = useState<TeamEffortResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `/api/effort/team/${encodeURIComponent(teamId)}?from=${from}&to=${to}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
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
  }, [from, to, teamId, token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <h3 style={{ margin: 0 }}>Team Effort: {teamId}</h3>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            style={inputStyle}
          />
          <span>to</span>
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            style={inputStyle}
          />
        </div>
      </div>

      {error && <div style={errorStyle}>{error}</div>}

      {loading ? (
        <p style={{ textAlign: "center", color: "#94a3b8" }}>Loading...</p>
      ) : data ? (
        <>
          {/* Summary bar */}
          <div style={summaryRow}>
            <span>
              Total: <strong>{data.total_hours.toFixed(1)}h</strong>
            </span>
            {EFFORT_CATEGORIES.map((c) => {
              const h = data.by_category[c];
              if (!h) return null;
              return (
                <span
                  key={c}
                  style={{ display: "flex", alignItems: "center", gap: 4 }}
                >
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      background: CATEGORY_COLORS[c],
                      display: "inline-block",
                    }}
                  />
                  {c}: {h.toFixed(1)}h
                </span>
              );
            })}
          </div>

          {/* By-day chart (horizontal bars) */}
          <h4 style={{ margin: "1rem 0 0.5rem", fontSize: "0.9rem" }}>
            Daily Breakdown
          </h4>
          <div style={{ maxHeight: 300, overflowY: "auto" }}>
            {data.by_day.map((d) => (
              <div key={d.day} style={barRow}>
                <span style={{ width: 90, fontSize: "0.8rem", flexShrink: 0 }}>
                  {d.day}
                </span>
                <div style={barTrack}>
                  {EFFORT_CATEGORIES.map((cat) => {
                    const val = d.by_category[cat];
                    if (!val) return null;
                    const pct = (val / 24) * 100;
                    return (
                      <div
                        key={cat}
                        title={`${cat}: ${val.toFixed(1)}h`}
                        style={{
                          width: `${pct}%`,
                          background: CATEGORY_COLORS[cat],
                          height: "100%",
                          minWidth: 2,
                        }}
                      />
                    );
                  })}
                </div>
                <span style={{ width: 50, textAlign: "right", fontSize: "0.8rem" }}>
                  {d.total_hours.toFixed(1)}h
                </span>
              </div>
            ))}
          </div>

          {/* Members table */}
          <h4 style={{ margin: "1rem 0 0.5rem", fontSize: "0.9rem" }}>
            Team Members
          </h4>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={th}>Member</th>
                <th style={th}>Total Hours</th>
                {EFFORT_CATEGORIES.map((c) => (
                  <th key={c} style={th}>
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: CATEGORY_COLORS[c],
                        display: "inline-block",
                        marginRight: 4,
                      }}
                    />
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.members.map((m) => (
                <tr key={m.person_id}>
                  <td style={td}>{m.display_name}</td>
                  <td style={{ ...td, fontWeight: 600 }}>
                    {m.total_hours.toFixed(1)}
                  </td>
                  {EFFORT_CATEGORIES.map((c) => (
                    <td key={c} style={td}>
                      {m.by_category[c]?.toFixed(1) ?? "-"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
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

const headerStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "1rem",
  flexWrap: "wrap",
  gap: "0.5rem",
};

const inputStyle: React.CSSProperties = {
  padding: "0.4rem",
  border: "1px solid #cbd5e1",
  borderRadius: 6,
  fontSize: "0.85rem",
};

const summaryRow: React.CSSProperties = {
  display: "flex",
  gap: "1rem",
  flexWrap: "wrap",
  fontSize: "0.85rem",
  marginBottom: "0.75rem",
  color: "#475569",
};

const errorStyle: React.CSSProperties = {
  background: "#fef2f2",
  color: "#dc2626",
  padding: "0.5rem 0.75rem",
  borderRadius: 6,
  marginBottom: "0.75rem",
  fontSize: "0.875rem",
};

const barRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
  marginBottom: 4,
};

const barTrack: React.CSSProperties = {
  flex: 1,
  height: 16,
  background: "#f1f5f9",
  borderRadius: 4,
  display: "flex",
  overflow: "hidden",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "0.8rem",
};

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "0.4rem",
  borderBottom: "2px solid #e2e8f0",
  fontWeight: 600,
  color: "#475569",
  whiteSpace: "nowrap",
};

const td: React.CSSProperties = {
  padding: "0.4rem",
  borderBottom: "1px solid #f1f5f9",
};
