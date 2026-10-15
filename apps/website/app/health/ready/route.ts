import { apiError, requestId } from "@ikun/runtime";
import { websiteReady } from "../../../lib/stores";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const id = requestId(request.headers.get("x-request-id"));
  const headers = { "cache-control": "no-store", "x-request-id": id };
  try {
    if (!await websiteReady()) throw new Error("DB_UNAVAILABLE");
    const hunter = Boolean(process.env.IKUN_HUNTER_ORIGIN && process.env.HUNTER_API_TOKEN);
    const tracking = Boolean(process.env.TRACKING_API_URL && process.env.TRACKING_API_TOKEN);
    // Configuration inventory only. Website readiness remains Auth + Projects IPC.
    return Response.json({ data: { service: "website", status: "ready", business_enabled: true, profile: 'c0-lite', workers_enabled: hunter || tracking,
      workers: { hunter: { configured: hunter }, tracking: { configured: tracking } } }, request_id: id }, { headers });
  } catch {
    return Response.json(apiError("DB_UNAVAILABLE", "Storage is unavailable", id, true), { status: 503, headers });
  }
}
