import { authorizeApiRequest } from "../../../../../lib/auth";
import { removeWatch } from "../../../../../lib/hackathon-watches";

export const dynamic = "force-dynamic";

export async function DELETE(request: Request, context: { params: Promise<{ id: string }> }) {
  const blocked = authorizeApiRequest(request);
  if (blocked) return blocked;
  const { id } = await context.params;
  if (!removeWatch(id)) return Response.json({ error: { message: "没有这条监控，或已经停止" } }, { status: 404 });
  return Response.json({ data: { id, removed: true } }, { headers: { "cache-control": "no-store" } });
}
