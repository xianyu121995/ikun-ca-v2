/** Website-owner integration candidate. No database access and no provider credentials. */
export async function trackingProxy(request: Request): Promise<Response> {
  const configured = process.env.TRACKING_API_URL;
  if (!configured) return Response.json({ detail: "Tracking service is not configured" }, { status: 503 });
  const origin = new URL(configured);
  if (origin.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(origin.hostname)
      || origin.username || origin.password || origin.pathname !== "/" || origin.search || origin.hash) {
    return Response.json({ detail: "Invalid tracking service configuration" }, { status: 503 });
  }
  const incoming = new URL(request.url);
  const path = incoming.pathname;
  if (!(path === "/tracking" || /^\/tracking-assets\/(app\.js|style\.css)$/.test(path)
      || path.startsWith("/api/tracking/") || path.startsWith("/api/v1/tracking/"))) {
    return Response.json({ detail: "Route not found" }, { status: 404 });
  }
  const headers = new Headers();
  for (const key of ["cookie", "origin", "content-type", "x-csrf-token", "x-tracking-csrf", "idempotency-key", "if-match", "x-request-id"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  headers.set("host", incoming.host);
  const timer = AbortSignal.timeout(10_000);
  try {
    const upstream = await fetch(new URL(path + incoming.search, origin), {
      method: request.method, headers, body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text(),
      cache: "no-store", redirect: "manual", signal: timer,
    });
    const result = new Headers();
    for (const key of ["content-type", "content-security-policy", "x-content-type-options", "referrer-policy", "etag", "x-request-id"]) {
      const value = upstream.headers.get(key);
      if (value) result.set(key, value);
    }
    result.set("cache-control", "no-store");
    // Main-site mode owns the session cookie. The BFF never creates a separate tracking login.
    return new Response(upstream.body, { status: upstream.status, headers: result });
  } catch {
    return Response.json({ detail: "Tracking service is unavailable" }, { status: 503 });
  }
}
