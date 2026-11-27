import { authorizeApiRequest } from "../../../../lib/auth";
import { generateHackathonAnalysis, type AnalysisEvidence } from "../../../../lib/hackathon-analysis";
import { locateProject, readHackathonSnapshot } from "../../../../lib/hackathon-snapshot";
import { officialHandle, saveAnalysis, tweetsForHandle } from "../../../../lib/hackathon-watches";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const blocked = authorizeApiRequest(request);
  if (blocked) return blocked;
  const body = await request.json().catch(() => null) as { event_id?: unknown; role?: unknown; name?: unknown } | null;
  if (typeof body?.event_id !== "string" || typeof body.role !== "string" || typeof body.name !== "string") {
    return Response.json({ error: { message: "分析缺少项目" } }, { status: 400 });
  }
  const loaded = readHackathonSnapshot(process.env.IKUN_HACKATHON_SNAPSHOT);
  if (!loaded.ok) return Response.json({ error: { message: "快照不可用，不能生成分析" } }, { status: 503 });
  const found = locateProject(loaded.snapshot, body.event_id, body.role, body.name);
  if (!found) return Response.json({ error: { message: "快照里没有这个官方项目" } }, { status: 404 });
  const handle = officialHandle(found.project.twitter) ?? "";
  const evidence: AnalysisEvidence = {
    event_title: found.event.title,
    official_status: found.event.official_status ?? "",
    name: found.project.name,
    role: found.project.role,
    place: found.project.place,
    track: found.project.track,
    info: found.project.info ?? "",
    website: found.project.website ?? "",
    handle,
    tweets: handle ? tweetsForHandle(handle) : [],
  };
  const generated = await generateHackathonAnalysis(evidence);
  if (!generated.ok) return Response.json({ error: { message: generated.message } }, { status: 503 });
  const analysis = saveAnalysis({ event_id: body.event_id, role: body.role, name: body.name, text: generated.text, thin: generated.thin });
  return Response.json({ data: { analysis } }, { headers: { "cache-control": "no-store" } });
}
