import type { AuthHttp } from "../../../../../../modules/auth/dist/src/http.js";
import { auth } from "../../../../../../modules/auth/dist/src/server.js";
import { authorizeApiRequest } from "../../../../lib/auth";
import { listHackathonTimeline } from "../../../../lib/hackathon-watches";

export const dynamic = "force-dynamic";

function allowTimelineRead() {
  const current = auth();
  const state = globalThis as typeof globalThis & { ikunAuth?: AuthHttp; ikunHackathonTimeline?: boolean };
  if (!state.ikunHackathonTimeline) {
    const Ctor = current.constructor as typeof AuthHttp;
    state.ikunAuth = new Ctor(current.store, [...current.readApi, /^\/api\/hackathons\/timeline$/], [...current.readPages]);
    state.ikunHackathonTimeline = true;
  }
}

export async function GET(request: Request) {
  allowTimelineRead();
  const blocked = authorizeApiRequest(request);
  if (blocked) return blocked;
  return Response.json({ data: { items: listHackathonTimeline() } }, { headers: { "cache-control": "no-store" } });
}
