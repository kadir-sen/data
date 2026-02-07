import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Proxy GET /api/effort/team/:teamId?from=&to= → backend */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ teamId: string }> },
) {
  const { teamId } = await params;
  const auth = req.headers.get("authorization") ?? "";
  const qs = req.nextUrl.search;
  const res = await fetch(`${API}/effort/team/${teamId}${qs}`, {
    headers: { Authorization: auth },
    cache: "no-store",
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
