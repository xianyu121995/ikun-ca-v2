import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { apiError, log, requestId, validBearer } from "./http.js";
import { closeStores, openStores, storesHealthy } from "./stores.js";

export async function startWorker(service: "hunter" | "tracking"): Promise<void> {
  const key = service.toUpperCase();
  const port = Number(process.env[`${key}_PORT`] ?? (service === "hunter" ? 3111 : 3112));
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("INVALID_PORT");
  const dataRoot = process.env.DATA_ROOT;
  if (!dataRoot) throw new Error("DATA_ROOT_REQUIRED");
  const stores = openStores(service, dataRoot);
  let draining = false;
  const respond = (res: ServerResponse, status: number, body: unknown, id: string) => {
    res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store", "x-request-id": id });
    res.end(JSON.stringify(body));
  };
  const handle = (req: IncomingMessage, res: ServerResponse) => {
    const supplied = req.headers["x-request-id"];
    const id = requestId(typeof supplied === "string" ? supplied : undefined);
    const pathname = new URL(req.url ?? "/", "http://127.0.0.1").pathname;
    if (req.method === "GET" && pathname === "/health/live") {
      return respond(res, 200, { data: { service, status: "alive", mode: "idle", external_io_enabled: false }, request_id: id }, id);
    }
    if (req.method === "GET" && pathname === "/health/ready") {
      const ready = !draining && storesHealthy(stores);
      return respond(res, ready ? 200 : 503, { data: { service, status: ready ? "ready" : "draining", mode: "idle", external_io_enabled: false }, request_id: id }, id);
    }
    if (pathname.startsWith("/internal/v1/")) {
      const token = process.env[`${key}_API_TOKEN`];
      if (!token || token.length < 32) return respond(res, 503, apiError("AUTH_NOT_CONFIGURED", "Internal API credential is not configured", id), id);
      if (!validBearer(req.headers.authorization, token)) return respond(res, 401, apiError("UNAUTHENTICATED", "Service credential required", id), id);
      if (req.method === "GET" && pathname === "/internal/v1/status") {
        return respond(res, 200, { data: { service, mode: "idle", external_io_enabled: false }, request_id: id }, id);
      }
      return respond(res, 501, apiError("NOT_IMPLEMENTED", "Business module is outside the foundation scope", id), id);
    }
    return respond(res, 404, apiError("NOT_FOUND", "Route not found", id), id);
  };
  const server = createServer((req, res) => {
    try { handle(req, res); } catch {
      const id = requestId(undefined);
      log(service, "request_failed", { code: "INTERNAL_ERROR", request_id: id });
      respond(res, 500, apiError("INTERNAL_ERROR", "Request failed", id), id);
    }
  });
  server.requestTimeout = 10_000;
  server.headersTimeout = 5_000;
  server.keepAliveTimeout = 5_000;
  server.maxConnections = 64;
  server.on("error", () => { closeStores(stores); log(service, "server_failed", { code: "LISTEN_FAILED" }); process.exitCode = 1; });
  await new Promise<void>((done, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", done);
  });
  log(service, "started", { port, pid: process.pid, mode: "idle" });
  const shutdown = () => {
    if (draining) return;
    draining = true;
    log(service, "draining");
    const deadline = setTimeout(() => { server.closeAllConnections(); closeStores(stores); process.exit(1); }, 10_000);
    deadline.unref();
    server.close(() => { clearTimeout(deadline); closeStores(stores); log(service, "stopped"); });
    server.closeIdleConnections();
  };
  process.once("SIGTERM", shutdown);
  process.once("SIGINT", shutdown);
}
