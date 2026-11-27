import { authorizeApiRequest } from "../../../../lib/auth";
import { addWatch, listTweets, listWatches, officialHandle } from "../../../../lib/hackathon-watches";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const blocked = authorizeApiRequest(request);
  if (blocked) return blocked;
  return Response.json({ data: { watches: listWatches(), tweets: listTweets() } }, { headers: { "cache-control": "no-store" } });
}

export async function POST(request: Request) {
  const blocked = authorizeApiRequest(request);
  if (blocked) return blocked;
  const body = await request.json().catch(() => null) as { handle?: unknown; twitter?: unknown; project_name?: unknown; event_title?: unknown; event_id?: unknown } | null;
  const handle = officialHandle(typeof body?.twitter === "string" ? body.twitter : "") || (typeof body?.handle === "string" ? body.handle.replace(/^@/, "") : "");
  if (!/^[A-Za-z0-9_]{1,15}$/.test(handle) || typeof body?.project_name !== "string") {
    return Response.json({ error: { message: "没有可监控的官方账号" } }, { status: 400 });
  }
  const watch = addWatch({
    handle,
    project_name: body.project_name,
    event_title: typeof body.event_title === "string" ? body.event_title : "",
    event_id: typeof body.event_id === "string" ? body.event_id : "",
  });
  return Response.json({ data: watch }, { headers: { "cache-control": "no-store" } });
}
