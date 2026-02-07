import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Proxy GET /api/effort/sprint/:sprintId → backend */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ sprintId: string }> },
) {
  const { sprintId } = await params;
  const auth = req.headers.get("authorization") ?? "";
  const res = await fetch(`${API}/effort/sprint/${sprintId}`, {
    headers: { Authorization: auth },
    cache: "no-store",
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
