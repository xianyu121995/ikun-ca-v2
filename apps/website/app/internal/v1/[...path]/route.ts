import { apiError, requestId, validBearer } from "@ikun/runtime";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
function unavailable(request: Request) {
  const id = requestId(request.headers.get("x-request-id"));
  const path = new URL(request.url).pathname;
  const token = path === "/internal/v1/ingest/hunter" ? process.env.PROJECTS_INGEST_HUNTER_TOKEN
    : path === "/internal/v1/ingest/tracking" ? process.env.PROJECTS_INGEST_TRACKING_TOKEN : undefined;
  const configured = Boolean(token && token.length >= 32);
  const authorized = validBearer(request.headers.get("authorization"), token);
  const status = !configured ? 503 : !authorized ? 401 : 501;
  const code = !configured ? "AUTH_NOT_CONFIGURED" : !authorized ? "UNAUTHENTICATED" : "NOT_IMPLEMENTED";
  return Response.json(apiError(code, "Project ingestion module is unavailable", id), { status, headers: { "cache-control": "no-store", "x-request-id": id } });
}
export const GET = unavailable;
export const POST = unavailable;
export const PATCH = unavailable;
export const DELETE = unavailable;
