"use client";

import { useCallback, useEffect, useState } from "react";

// ── Types ──────────────────────────────────────────────────────────
interface Connector {
  id: string;
  source: string;
  label: string;
  scopes: string | null;
  is_service_account: boolean;
  created_at: string;
  updated_at: string;
}

const SOURCES = [
  {
    key: "jira",
    name: "Jira",
    description: "Issues, sprints, boards",
    scopes: "read:jira-work, read:jira-user",
  },
  {
    key: "gitlab",
    name: "GitLab",
    description: "Projects, MRs, time tracking",
    scopes: "read_api, read_user",
  },
  {
    key: "slack",
    name: "Slack",
    description: "Channels, activity correlation",
    scopes: "channels:read, users:read",
  },
  {
    key: "notion",
    name: "Notion",
    description: "Pages, databases, blocks",
    scopes: "read_content, read_users",
  },
  {
    key: "google",
    name: "Google Workspace",
    description: "Calendar, Drive metadata",
    scopes: "calendar.readonly, drive.metadata.readonly",
  },
] as const;

// ── Helpers ────────────────────────────────────────────────────────
const API_BASE =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
    : "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

async function apiFetchAuth<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `API ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Component ──────────────────────────────────────────────────────
export default function ConnectorsPage() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectingSource, setConnectingSource] = useState<string | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [labelInput, setLabelInput] = useState("");

  const fetchConnectors = useCallback(async () => {
    try {
      const data = await apiFetchAuth<{ connectors: Connector[] }>("/connectors");
      setConnectors(data.connectors);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load connectors");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConnectors();
  }, [fetchConnectors]);

  const handleConnect = async (sourceKey: string) => {
    if (!tokenInput.trim()) return;
    try {
      const sourceInfo = SOURCES.find((s) => s.key === sourceKey);
      await apiFetchAuth<Connector>("/connectors", {
        method: "POST",
        body: JSON.stringify({
          source: sourceKey,
          token: tokenInput,
          label: labelInput || `${sourceInfo?.name ?? sourceKey} connection`,
          scopes: sourceInfo?.scopes ?? null,
        }),
      });
      setTokenInput("");
      setLabelInput("");
      setConnectingSource(null);
      await fetchConnectors();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    }
  };

  const handleDisconnect = async (connectorId: string) => {
    try {
      await apiFetchAuth(`/connectors/${connectorId}`, { method: "DELETE" });
      await fetchConnectors();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to disconnect");
    }
  };

  const connectedSources = new Set(connectors.map((c) => c.source));

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 800 }}>
      <h1>Connectors</h1>
      <p style={{ color: "#666" }}>
        Connect your project tools to aggregate data into Case dashboards.
      </p>

      {error && (
        <div
          style={{
            background: "#fee",
            border: "1px solid #c00",
            padding: "0.75rem 1rem",
            borderRadius: 4,
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      {loading ? (
        <p>Loading connectors…</p>
      ) : (
        <>
          {/* Connected sources */}
          {connectors.length > 0 && (
            <section style={{ marginBottom: "2rem" }}>
              <h2>Connected</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {connectors.map((c) => (
                  <div
                    key={c.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "0.75rem 1rem",
                      border: "1px solid #ccc",
                      borderRadius: 6,
                      background: "#f9f9f9",
                    }}
                  >
                    <div>
                      <strong style={{ textTransform: "capitalize" }}>{c.source}</strong>
                      {c.label && (
                        <span style={{ color: "#666", marginLeft: 8 }}>— {c.label}</span>
                      )}
                      {c.is_service_account && (
                        <span
                          style={{
                            marginLeft: 8,
                            fontSize: "0.75rem",
                            background: "#e0e7ff",
                            padding: "2px 6px",
                            borderRadius: 3,
                          }}
                        >
                          Service Account
                        </span>
                      )}
                      <div style={{ fontSize: "0.8rem", color: "#888", marginTop: 2 }}>
                        Connected {new Date(c.created_at).toLocaleDateString()}
                        {c.scopes && ` · Scopes: ${c.scopes}`}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDisconnect(c.id)}
                      style={{
                        background: "#dc2626",
                        color: "#fff",
                        border: "none",
                        padding: "6px 14px",
                        borderRadius: 4,
                        cursor: "pointer",
                      }}
                    >
                      Disconnect
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Available sources */}
          <section>
            <h2>Available Sources</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {SOURCES.map((src) => {
                const isConnected = connectedSources.has(src.key);
                const isExpanded = connectingSource === src.key;

                return (
                  <div
                    key={src.key}
                    style={{
                      padding: "0.75rem 1rem",
                      border: "1px solid #ccc",
                      borderRadius: 6,
                      background: isConnected ? "#f0fdf4" : "#fff",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                      }}
                    >
                      <div>
                        <strong>{src.name}</strong>
                        <div style={{ fontSize: "0.85rem", color: "#666" }}>
                          {src.description}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "#999" }}>
                          Scopes: {src.scopes}
                        </div>
                      </div>
                      {!isExpanded && (
                        <button
                          onClick={() => {
                            setConnectingSource(src.key);
                            setTokenInput("");
                            setLabelInput("");
                          }}
                          style={{
                            background: isConnected ? "#16a34a" : "#2563eb",
                            color: "#fff",
                            border: "none",
                            padding: "6px 14px",
                            borderRadius: 4,
                            cursor: "pointer",
                          }}
                        >
                          {isConnected ? "Add Another" : "Connect"}
                        </button>
                      )}
                    </div>

                    {isExpanded && (
                      <div style={{ marginTop: "0.75rem" }}>
                        <input
                          type="text"
                          placeholder="Label (optional)"
                          value={labelInput}
                          onChange={(e) => setLabelInput(e.target.value)}
                          style={{
                            display: "block",
                            width: "100%",
                            padding: "6px 10px",
                            marginBottom: 8,
                            border: "1px solid #ccc",
                            borderRadius: 4,
                            boxSizing: "border-box",
                          }}
                        />
                        <input
                          type="password"
                          placeholder="API token / access token"
                          value={tokenInput}
                          onChange={(e) => setTokenInput(e.target.value)}
                          style={{
                            display: "block",
                            width: "100%",
                            padding: "6px 10px",
                            marginBottom: 8,
                            border: "1px solid #ccc",
                            borderRadius: 4,
                            boxSizing: "border-box",
                          }}
                        />
                        <div style={{ display: "flex", gap: 8 }}>
                          <button
                            onClick={() => handleConnect(src.key)}
                            disabled={!tokenInput.trim()}
                            style={{
                              background: tokenInput.trim() ? "#2563eb" : "#94a3b8",
                              color: "#fff",
                              border: "none",
                              padding: "6px 14px",
                              borderRadius: 4,
                              cursor: tokenInput.trim() ? "pointer" : "not-allowed",
                            }}
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setConnectingSource(null)}
                            style={{
                              background: "#e5e7eb",
                              color: "#333",
                              border: "none",
                              padding: "6px 14px",
                              borderRadius: 4,
                              cursor: "pointer",
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
