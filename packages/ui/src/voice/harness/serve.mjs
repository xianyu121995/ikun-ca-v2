/** Run this foreground server only under the repository's shared heavy lock. Mock audio only. */
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const result = await build({ absWorkingDir: root, entryPoints: [fileURLToPath(new URL("main.mjs", import.meta.url))], outdir: "voice-harness", bundle: true, write: false, metafile: true, format: "esm", platform: "browser", jsx: "automatic", target: "es2022", sourcemap: "inline", define: { "process.env.NODE_ENV": '"development"' } });
const inputs = {};
for (const name of Object.keys(result.metafile.inputs)) if (!name.includes("node_modules/")) inputs[name] = createHash("sha256").update(await readFile(resolve(root, name))).digest("hex");
const evidence = new URL("../../../var/voice/", import.meta.url); await mkdir(evidence, { recursive: true });
await writeFile(new URL("browser-inputs.json", evidence), JSON.stringify({ inputs, warnings: result.warnings.map(v => v.text), audio: "mock-only" }, null, 2));
const js = result.outputFiles.find(v => v.path.endsWith(".js"))?.contents;
const css = result.outputFiles.find(v => v.path.endsWith(".css"))?.contents;
if (!js || !css) throw Error("Harness assets missing");
const html = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Voice mock acceptance</title><link rel="stylesheet" href="/harness.css"></head><body style="margin:0;background:#0b0e12"><div id="root"></div><script type="module" src="/harness.js"></script></body></html>';
const server = createServer((request, response) => {
  if (!["GET", "HEAD"].includes(request.method)) { response.writeHead(405); response.end(); return; }
  const asset = request.url === "/" ? ["text/html", html] : request.url === "/harness.js" ? ["text/javascript", js] : request.url === "/harness.css" ? ["text/css", css] : null;
  if (!asset) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { "content-type": asset[0] + "; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff", "content-security-policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'none'; media-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" }); response.end(request.method === "HEAD" ? undefined : asset[1]);
});
server.requestTimeout = 10000; server.headersTimeout = 10000;
server.on("error", () => { console.error("VOICE_HARNESS_START_FAILED"); process.exitCode = 1; });
server.listen(3260, "127.0.0.1", () => console.log("VOICE_MOCK_HARNESS http://127.0.0.1:3260 · no real speech"));
for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => { server.closeAllConnections(); server.close(); });
