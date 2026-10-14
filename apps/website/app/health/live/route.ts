import { requestId } from "@ikun/runtime";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export function GET(request: Request) {
  const id = requestId(request.headers.get("x-request-id"));
  return Response.json({ data: { service: "website", status: "alive" }, request_id: id }, { headers: { "cache-control": "no-store", "x-request-id": id } });
}
