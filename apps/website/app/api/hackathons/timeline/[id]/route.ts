import { authorizeApiRequest } from "../../../../../lib/auth";
import { deleteHackathonTimelineEntry, updateHackathonTimelineEntry } from "../../../../../lib/hackathon-watches";

export const dynamic = "force-dynamic";

export async function PATCH(request: Request, context: { params: Promise<{ id: string }> }) {
  const blocked = authorizeApiRequest(request);
  if (blocked) return blocked;
  const body = await request.json().catch(() => null) as { date?: unknown; hour?: unknown; title?: unknown; status?: unknown } | null;
  if (!body || typeof body.date !== "string" || typeof body.title !== "string" || (body.status !== "confirmed" && body.status !== "estimated")) {
    return Response.json({ error: { message: "时间点字段不正确" } }, { status: 400 });
  }
  const hour = body.hour === null ? null : typeof body.hour === "string" ? body.hour : undefined;
  if (hour === undefined) return Response.json({ error: { message: "时间点字段不正确" } }, { status: 400 });
  const { id } = await context.params;
  if (!updateHackathonTimelineEntry(id, { date: body.date, hour, title: body.title, status: body.status })) {
    return Response.json({ error: { message: "没有这条黑客松时间点" } }, { status: 404 });
  }
  return Response.json({ data: { id, ...body } }, { headers: { "cache-control": "no-store" } });
}

export async function DELETE(request: Request, context: { params: Promise<{ id: string }> }) {
  const blocked = authorizeApiRequest(request);
  if (blocked) return blocked;
  const { id } = await context.params;
  if (!deleteHackathonTimelineEntry(id)) return Response.json({ error: { message: "没有这条黑客松时间点" } }, { status: 404 });
  return Response.json({ data: { id, removed: true } }, { headers: { "cache-control": "no-store" } });
}
