import { apiError, requestId } from "@ikun/runtime";
import { websiteReady } from "../../../lib/stores";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export function GET(request: Request) {
  const id = requestId(request.headers.get("x-request-id"));
  const headers = { "cache-control": "no-store", "x-request-id": id };
  try {
    if (!websiteReady()) throw new Error("DB_UNAVAILABLE");
    return Response.json({ data: { service: "website", status: "ready", business_enabled: false }, request_id: id }, { headers });
  } catch {
    return Response.json(apiError("DB_UNAVAILABLE", "Storage is unavailable", id, true), { status: 503, headers });
  }
}
