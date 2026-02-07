import { NextResponse } from "next/server";

/** Proxy route so browser clients can call /api/healthz without CORS. */
export async function GET() {
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${base}/healthz`, { cache: "no-store" });
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { status: "unreachable", version: "unknown" },
      { status: 502 }
    );
  }
}
