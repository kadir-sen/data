import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Proxy PUT/DELETE /api/effort/:effortId → backend */
export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ effortId: string }> },
) {
  const { effortId } = await params;
  const auth = req.headers.get("authorization") ?? "";
  const body = await req.json();
  const res = await fetch(`${API}/effort/${effortId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: auth },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ effortId: string }> },
) {
  const { effortId } = await params;
  const auth = req.headers.get("authorization") ?? "";
  const res = await fetch(`${API}/effort/${effortId}`, {
    method: "DELETE",
    headers: { Authorization: auth },
  });
  if (res.status === 204) return new NextResponse(null, { status: 204 });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
