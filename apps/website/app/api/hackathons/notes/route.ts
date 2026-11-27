import { authorizeApiRequest } from "../../../../lib/auth";
import { locateProject, readHackathonSnapshot } from "../../../../lib/hackathon-snapshot";
import { saveNote } from "../../../../lib/hackathon-watches";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const blocked = authorizeApiRequest(request);
  if (blocked) return blocked;
  const body = await request.json().catch(() => null) as { event_id?: unknown; role?: unknown; name?: unknown; text?: unknown } | null;
  if (typeof body?.event_id !== "string" || typeof body.role !== "string" || typeof body.name !== "string" || typeof body.text !== "string") {
    return Response.json({ error: { message: "备注缺少项目" } }, { status: 400 });
  }
  const loaded = readHackathonSnapshot(process.env.IKUN_HACKATHON_SNAPSHOT);
  if (!loaded.ok) return Response.json({ error: { message: "快照不可用，不能保存备注" } }, { status: 503 });
  if (!locateProject(loaded.snapshot, body.event_id, body.role, body.name)) {
    return Response.json({ error: { message: "快照里没有这个官方项目" } }, { status: 404 });
  }
  const note = saveNote({ event_id: body.event_id, role: body.role, name: body.name, text: body.text });
  return Response.json({ data: { note } }, { headers: { "cache-control": "no-store" } });
}
