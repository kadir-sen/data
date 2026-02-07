"use client";

import { FormEvent, useState } from "react";
import { EFFORT_CATEGORIES, type EffortCategory } from "@/lib/effort-types";

interface Props {
  token: string;
  onCreated?: () => void;
}

export default function EffortForm({ token, onCreated }: Props) {
  const today = new Date().toISOString().slice(0, 10);
  const [day, setDay] = useState(today);
  const [hours, setHours] = useState("");
  const [plannedHours, setPlannedHours] = useState("");
  const [category, setCategory] = useState<EffortCategory>("development");
  const [description, setDescription] = useState("");
  const [workItemId, setWorkItemId] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    const payload: Record<string, unknown> = {
      day,
      hours: parseFloat(hours),
      category,
      description: description || null,
      work_item_id: workItemId || null,
      planned_hours: plannedHours ? parseFloat(plannedHours) : null,
    };

    try {
      const res = await fetch("/api/effort", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || `Error ${res.status}`);
        return;
      }
      // Reset form
      setHours("");
      setPlannedHours("");
      setDescription("");
      setWorkItemId("");
      onCreated?.();
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={formStyle}>
      <h3 style={{ margin: "0 0 0.75rem" }}>Log Effort</h3>

      {error && <div style={errorStyle}>{error}</div>}

      <div style={rowStyle}>
        <label style={labelStyle}>
          Date
          <input
            type="date"
            value={day}
            onChange={(e) => setDay(e.target.value)}
            required
            style={inputStyle}
          />
        </label>

        <label style={labelStyle}>
          Hours *
          <input
            type="number"
            step="0.25"
            min="0.25"
            max="24"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            required
            style={inputStyle}
          />
        </label>

        <label style={labelStyle}>
          Planned Hours
          <input
            type="number"
            step="0.25"
            min="0"
            max="24"
            value={plannedHours}
            onChange={(e) => setPlannedHours(e.target.value)}
            style={inputStyle}
          />
        </label>
      </div>

      <div style={rowStyle}>
        <label style={labelStyle}>
          Category
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as EffortCategory)}
            style={inputStyle}
          >
            {EFFORT_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>

        <label style={{ ...labelStyle, flex: 2 }}>
          Work Item ID (optional)
          <input
            type="text"
            value={workItemId}
            onChange={(e) => setWorkItemId(e.target.value)}
            placeholder="UUID of linked work item"
            style={inputStyle}
          />
        </label>
      </div>

      <label style={labelStyle}>
        Note
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="What did you work on?"
          style={{ ...inputStyle, resize: "vertical" }}
        />
      </label>

      <button type="submit" disabled={submitting} style={btnStyle}>
        {submitting ? "Saving..." : "Save Entry"}
      </button>
    </form>
  );
}

const formStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #e2e8f0",
  borderRadius: 8,
  padding: "1.25rem",
  marginBottom: "1.5rem",
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  gap: "1rem",
  marginBottom: "0.75rem",
  flexWrap: "wrap",
};

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: "0.875rem",
  fontWeight: 500,
  flex: 1,
  minWidth: 140,
};

const inputStyle: React.CSSProperties = {
  padding: "0.5rem",
  border: "1px solid #cbd5e1",
  borderRadius: 6,
  fontSize: "0.875rem",
};

const btnStyle: React.CSSProperties = {
  marginTop: "0.5rem",
  padding: "0.5rem 1.25rem",
  background: "#3b82f6",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  fontWeight: 600,
  cursor: "pointer",
};

const errorStyle: React.CSSProperties = {
  background: "#fef2f2",
  color: "#dc2626",
  padding: "0.5rem 0.75rem",
  borderRadius: 6,
  marginBottom: "0.75rem",
  fontSize: "0.875rem",
};
