import { apiError, requestId } from "@ikun/runtime";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
function unavailable(request: Request) {
  const id = requestId(request.headers.get("x-request-id"));
  return Response.json(apiError("AUTH_NOT_CONFIGURED", "Authentication module has not been implemented", id), {
    status: 503, headers: { "cache-control": "no-store", "x-request-id": id },
  });
}
export const GET = unavailable;
export const POST = unavailable;
export const PATCH = unavailable;
export const PUT = unavailable;
export const DELETE = unavailable;
