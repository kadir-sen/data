/**
 * Lightweight fetch wrapper for calling the API from client components.
 * Once packages/shared generates a typed OpenAPI client, prefer that instead.
 */

const API_BASE =
  typeof window !== "undefined"
    ? "/api" // browser → Next.js proxy routes
    : (process.env.API_INTERNAL_URL ?? "http://localhost:8000"); // server → direct

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}
