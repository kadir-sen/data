"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CATEGORY_COLORS,
  EFFORT_CATEGORIES,
  type EffortCategory,
  type EffortLogEntry,
} from "@/lib/effort-types";

interface Props {
  token: string;
  refreshKey?: number;
}

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}
function endOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}
function fmt(d: Date) {
  return d.toISOString().slice(0, 10);
}

export default function MyEffort({ token, refreshKey }: Props) {
  const [month, setMonth] = useState(() => new Date());
  const [entries, setEntries] = useState<EffortLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"calendar" | "list">("calendar");

  const from = fmt(startOfMonth(month));
  const to = fmt(endOfMonth(month));

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/effort/me?from=${from}&to=${to}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setEntries(await res.json());
    } finally {
      setLoading(false);
    }
  }, [from, to, token]);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshKey]);

  const prevMonth = () =>
    setMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1));
  const nextMonth = () =>
    setMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1));

  // Group by day
  const byDay: Record<string, EffortLogEntry[]> = {};
  for (const e of entries) {
    (byDay[e.day] ??= []).push(e);
  }

  // Calendar grid
  const start = startOfMonth(month);
  const end = endOfMonth(month);
  const startDow = start.getDay(); // 0=Sun
  const totalDays = end.getDate();

  const monthLabel = month.toLocaleString("default", {
    month: "long",
    year: "numeric",
  });

  const totalHours = entries.reduce((s, e) => s + e.hours, 0);

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <h3 style={{ margin: 0 }}>My Effort</h3>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button onClick={prevMonth} style={navBtn}>
            &lt;
          </button>
          <span style={{ fontWeight: 600, minWidth: 150, textAlign: "center" }}>
            {monthLabel}
          </span>
          <button onClick={nextMonth} style={navBtn}>
            &gt;
          </button>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            onClick={() => setView("calendar")}
            style={view === "calendar" ? activeTab : tab}
          >
            Calendar
          </button>
          <button
            onClick={() => setView("list")}
            style={view === "list" ? activeTab : tab}
          >
            List
          </button>
        </div>
      </div>

      <div style={summaryRow}>
        <span>
          Total: <strong>{totalHours.toFixed(1)}h</strong>
        </span>
        {EFFORT_CATEGORIES.map((c) => {
          const h = entries
            .filter((e) => e.category === c)
            .reduce((s, e) => s + e.hours, 0);
          if (h === 0) return null;
          return (
            <span key={c} style={{ display: "flex", alignItems: "center", gap: 4 }}>
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

      {loading ? (
        <p style={{ textAlign: "center", color: "#94a3b8" }}>Loading...</p>
      ) : view === "calendar" ? (
        <CalendarView
          startDow={startDow}
          totalDays={totalDays}
          byDay={byDay}
          month={month}
        />
      ) : (
        <ListView entries={entries} />
      )}
    </div>
  );
}

function CalendarView({
  startDow,
  totalDays,
  byDay,
  month,
}: {
  startDow: number;
  totalDays: number;
  byDay: Record<string, EffortLogEntry[]>;
  month: Date;
}) {
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const cells: (number | null)[] = Array(startDow).fill(null);
  for (let d = 1; d <= totalDays; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div style={calGrid}>
      {days.map((d) => (
        <div key={d} style={calHeader}>
          {d}
        </div>
      ))}
      {cells.map((d, i) => {
        if (d === null) return <div key={`e${i}`} style={calCell} />;
        const dayStr = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        const dayEntries = byDay[dayStr] || [];
        const h = dayEntries.reduce((s, e) => s + e.hours, 0);
        return (
          <div
            key={d}
            style={{
              ...calCell,
              background: h > 0 ? "#f0f9ff" : "#fff",
            }}
            title={dayEntries.map((e) => `${e.category}: ${e.hours}h`).join("\n")}
          >
            <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{d}</div>
            {h > 0 && (
              <div style={{ fontWeight: 600, fontSize: "0.8rem" }}>{h.toFixed(1)}h</div>
            )}
            {dayEntries.length > 0 && (
              <div style={{ display: "flex", gap: 2, flexWrap: "wrap", marginTop: 2 }}>
                {dayEntries.map((e) => (
                  <span
                    key={e.id}
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: CATEGORY_COLORS[e.category as EffortCategory] ?? "#999",
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ListView({ entries }: { entries: EffortLogEntry[] }) {
  if (entries.length === 0) {
    return (
      <p style={{ textAlign: "center", color: "#94a3b8", padding: "2rem" }}>
        No effort entries for this period.
      </p>
    );
  }

  return (
    <table style={tableStyle}>
      <thead>
        <tr>
          <th style={th}>Date</th>
          <th style={th}>Hours</th>
          <th style={th}>Planned</th>
          <th style={th}>Category</th>
          <th style={th}>Note</th>
          <th style={th}>Locked</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr key={e.id}>
            <td style={td}>{e.day}</td>
            <td style={td}>{e.hours}</td>
            <td style={td}>{e.planned_hours ?? "-"}</td>
            <td style={td}>
              <span
                style={{
                  ...categoryBadge,
                  background: CATEGORY_COLORS[e.category] ?? "#e2e8f0",
                }}
              >
                {e.category}
              </span>
            </td>
            <td style={td}>{e.description || "-"}</td>
            <td style={td}>{e.locked ? "Yes" : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
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

const summaryRow: React.CSSProperties = {
  display: "flex",
  gap: "1rem",
  flexWrap: "wrap",
  fontSize: "0.85rem",
  marginBottom: "1rem",
  color: "#475569",
};

const navBtn: React.CSSProperties = {
  background: "#f1f5f9",
  border: "1px solid #cbd5e1",
  borderRadius: 4,
  padding: "0.25rem 0.5rem",
  cursor: "pointer",
};

const tab: React.CSSProperties = {
  background: "transparent",
  border: "1px solid #cbd5e1",
  borderRadius: 4,
  padding: "0.25rem 0.75rem",
  cursor: "pointer",
  fontSize: "0.8rem",
};

const activeTab: React.CSSProperties = {
  ...tab,
  background: "#3b82f6",
  color: "#fff",
  borderColor: "#3b82f6",
};

const calGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(7, 1fr)",
  gap: 2,
};

const calHeader: React.CSSProperties = {
  textAlign: "center",
  fontWeight: 600,
  fontSize: "0.75rem",
  color: "#64748b",
  padding: "0.25rem",
};

const calCell: React.CSSProperties = {
  minHeight: 60,
  border: "1px solid #f1f5f9",
  borderRadius: 4,
  padding: 4,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "0.85rem",
};

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "0.5rem",
  borderBottom: "2px solid #e2e8f0",
  fontWeight: 600,
  color: "#475569",
};

const td: React.CSSProperties = {
  padding: "0.5rem",
  borderBottom: "1px solid #f1f5f9",
};

const categoryBadge: React.CSSProperties = {
  padding: "2px 8px",
  borderRadius: 12,
  color: "#fff",
  fontSize: "0.75rem",
  fontWeight: 500,
};
