// Isolated rejection fixture for presentation tests; no Auth service or database.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Alert, LoginPanel } from "../dist/index.js";

function documentHtml(content) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>UI0 无脚本安全回退测试</title><link rel="stylesheet" href="/styles.css"></head><body style="margin:0">${content}</body></html>`;
}
export async function createNoJsFixture(port = 0) {
  const observations = [];
  const styles = await readFile(new URL("../dist/styles.css", import.meta.url));
  const login = documentHtml(renderToStaticMarkup(createElement(LoginPanel, {
    onSubmit() {}, notice: createElement(Alert, { tone: "warning", title: "无脚本安全回退测试 · 虚构凭据专用" }, "此页不加载任何 JavaScript，不连接认证服务。提交固定同源 POST，随后安全拒绝。"),
  })));
  const rejected = documentHtml(renderToStaticMarkup(createElement("div", { className: "ik-theme ik-auth-layout" }, createElement(Alert, { tone: "danger", title: "安全回退：表单提交已拒绝", code: "UI_FIXTURE_ONLY" }, "不支持表单编码。没有执行认证，没有保存或回显凭据。这是 UI0 隔离测试夹具。"))));
  const headers = {
    "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; script-src 'none'; style-src 'self' 'unsafe-inline'; connect-src 'none'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
  };
  const server = createServer({ requestTimeout: 5000, headersTimeout: 5000 }, (request, response) => {
    const url = new URL(request.url ?? "/", "http://127.0.0.1");
    if (url.pathname === "/api/v1/auth/login") {
      const observation = { method: request.method, request_path: url.pathname, query_present: Boolean(url.search), credential_query_present: ["password", "username"].some(name => url.searchParams.has(name)), body_bytes: 0 };
      observations.push(observation);
      request.on("data", chunk => { observation.body_bytes += chunk.length; }); // Count only, never retain body.
      request.on("end", () => { response.writeHead(request.method === "POST" ? (observation.body_bytes > 8192 ? 413 : 415) : 405, headers); response.end(rejected); });
      return;
    }
    if (request.method === "GET" && url.pathname === "/") { response.writeHead(200, headers); response.end(login); return; }
    if (request.method === "GET" && url.pathname === "/styles.css") { response.writeHead(200, { ...headers, "Content-Type": "text/css; charset=utf-8" }); response.end(styles); return; }
    if (request.method === "GET" && url.pathname === "/observations") { response.writeHead(200, { ...headers, "Content-Type": "application/json" }); response.end(JSON.stringify(observations)); return; }
    response.writeHead(404, headers); response.end("UI fixture route not found");
  });
  await new Promise((resolve, reject) => { server.once("error", reject); server.listen(port, "127.0.0.1", resolve); });
  const address = server.address();
  return { server, origin: `http://127.0.0.1:${address.port}`, observations };
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const index = process.argv.indexOf("--port"); const port = Number(index >= 0 ? process.argv[index + 1] : 3251);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("Use --port with an integer from 1024 to 65535");
  const { server, origin } = await createNoJsFixture(port);
  console.log(`UI0 no-JS rejection fixture · ${origin} · no Auth/API integration`);
  for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => { server.closeAllConnections(); server.close(); });
}
