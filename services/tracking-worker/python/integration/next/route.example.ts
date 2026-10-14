// Copy this thin handler to each assigned website route; keep the shared helper in lib/tracking-proxy.ts.
// app/tracking/route.ts
// app/tracking-assets/[asset]/route.ts
// app/api/tracking/[...path]/route.ts
// app/api/v1/tracking/[...path]/route.ts
// Adjust the relative import for the destination, or use the website's configured alias.
import { trackingProxy } from "./tracking-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const GET = trackingProxy;
export const POST = trackingProxy;
export const PATCH = trackingProxy;
export const DELETE = trackingProxy;
