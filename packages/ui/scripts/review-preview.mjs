import { createServer } from "node:http";
import { mkdir, writeFile } from "node:fs/promises";
import { buildReview } from "./review-build.mjs";

const index = process.argv.indexOf("--port"); const port = Number(index >= 0 ? process.argv[index + 1] : 3255);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("Invalid review port");
const { js, css, manifest, inputHashes, warnings } = await buildReview();
const evidenceDir = new URL("../var/final-review/", import.meta.url); await mkdir(evidenceDir, { recursive: true });
await writeFile(new URL("sources.json", evidenceDir), JSON.stringify({ manifest, inputHashes, warnings }, null, 2));
const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ikun.ca · 三页定稿联调</title><link rel="stylesheet" href="/review.css"></head><body><div id="root"></div><script type="module" src="/review.js"></script></body></html>`;
const server = createServer({ requestTimeout: 10000, headersTimeout: 10000 }, (request, response) => {
  const path = new URL(request.url ?? "/", `http://127.0.0.1:${port}`).pathname;
  if (request.method !== "GET" && request.method !== "HEAD") { response.writeHead(405, { Allow: "GET, HEAD" }); response.end("UI review only"); return; }
  const asset = path === "/review.js" ? ["text/javascript; charset=utf-8", js] : path === "/review.css" ? ["text/css; charset=utf-8", css] : ["/", "/hunter", "/tracking"].includes(path) ? ["text/html; charset=utf-8", html] : undefined;
  if (!asset) { response.writeHead(404); response.end("Not found"); return; }
  response.writeHead(200, { "Content-Type": asset[0], "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'none'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'" });
  response.end(request.method === "HEAD" ? undefined : asset[1]);
});
server.on("error", error => { console.error(`UI review failed: ${error.message}`); process.exitCode = 1; });
server.listen(port, "127.0.0.1", () => console.log(`Three approved UI designs · http://127.0.0.1:${port} · demo only`));
for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => { server.closeAllConnections(); server.close(); });
