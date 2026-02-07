import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Proxy GET /api/effort/me?from=&to= → backend */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";
  const qs = req.nextUrl.search;
  const res = await fetch(`${API}/effort/me${qs}`, {
    headers: { Authorization: auth },
    cache: "no-store",
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
