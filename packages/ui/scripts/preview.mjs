import { build } from "esbuild";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const argIndex = process.argv.indexOf("--port");
const port = Number(argIndex >= 0 ? process.argv[argIndex + 1] : 3150);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("Use --port with an integer from 1024 to 65535");
const result = await build({
  entryPoints: [fileURLToPath(new URL("../preview/main.tsx", import.meta.url))],
  bundle: true, write: false, outdir: "preview", platform: "browser", format: "esm", jsx: "automatic",
  define: { "process.env.NODE_ENV": '"development"' }, sourcemap: "inline",
});
const script = result.outputFiles.find(file => file.path.endsWith(".js"))?.contents;
const styles = result.outputFiles.find(file => file.path.endsWith(".css"))?.contents;
if (!script || !styles) throw new Error("Preview build did not produce JavaScript and CSS");
const html = await readFile(new URL("../preview/index.html", import.meta.url));
const assets = new Map([["/", ["text/html; charset=utf-8", html]], ["/preview.js", ["text/javascript; charset=utf-8", script]], ["/preview.css", ["text/css; charset=utf-8", styles]]]);
const server = createServer({ requestTimeout: 10000, headersTimeout: 10000 }, (request, response) => {
  const pathname = new URL(request.url ?? "/", `http://127.0.0.1:${port}`).pathname;
  if (request.method !== "GET" && request.method !== "HEAD") { response.writeHead(405, { Allow: "GET, HEAD" }); response.end(); return; }
  const asset = assets.get(pathname);
  if (!asset) { response.writeHead(404); response.end("Not found"); return; }
  response.writeHead(200, { "Content-Type": asset[0], "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; frame-ancestors 'none'" });
  response.end(request.method === "HEAD" ? undefined : asset[1]);
});
server.on("error", error => { console.error(`UI preview failed: ${error.message}`); process.exitCode = 1; });
server.listen(port, "127.0.0.1", () => console.log(`UI components only · http://127.0.0.1:${port} · no backend or database`));
let stopping = false;
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => {
  if (stopping) return; stopping = true;
  const timer = setTimeout(() => { server.closeAllConnections(); process.exit(1); }, 3000); timer.unref();
  server.close(() => { clearTimeout(timer); process.exit(0); });
});
