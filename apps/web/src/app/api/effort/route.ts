import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Proxy POST /api/effort → backend POST /effort */
export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";
  const body = await req.json();
  const res = await fetch(`${API}/effort`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: auth },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

/** Proxy GET /api/effort?... → backend GET /effort?... */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";
  const qs = req.nextUrl.search;
  const res = await fetch(`${API}/effort${qs}`, {
    headers: { Authorization: auth },
    cache: "no-store",
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
