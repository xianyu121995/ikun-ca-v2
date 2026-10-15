import { test } from "node:test";
import assert from "node:assert/strict";
import { createNoJsFixture } from "../scripts/no-js-fixture.mjs";

test("unbound LoginPanel submits a fixed same-origin POST without leaking credentials in URLs or responses", async t => {
  const fixture = await createNoJsFixture();
  t.after(async () => { fixture.server.closeAllConnections(); await new Promise(resolve => fixture.server.close(resolve)); });
  const page = await fetch(fixture.origin, { signal: AbortSignal.timeout(5000) });
  const html = await page.text();
  const form = html.match(/<form\b[^>]*>/)?.[0]; assert.ok(form);
  assert.match(form, /method="post"/); assert.match(form, /action="\/api\/v1\/auth\/login"/);
  assert.doesNotMatch(html, /<script\b/); assert.match(page.headers.get("content-security-policy"), /script-src 'none'/);
  const action = form.match(/action="([^"]+)"/)[1];
  const target = new URL(action, fixture.origin); assert.equal(target.origin, fixture.origin); assert.equal(target.search, "");
  const password = "fictional-ui0-only-password";
  const response = await fetch(target, { method: "POST", body: new URLSearchParams({ username: "fictional-ui0", password }), redirect: "error", signal: AbortSignal.timeout(5000) });
  assert.equal(response.status, 415); assert.equal(new URL(response.url).search, ""); assert.ok(!response.url.includes(password));
  const errorHtml = await response.text(); assert.match(errorHtml, /安全回退：表单提交已拒绝/); assert.ok(!errorHtml.includes(password));
  assert.deepEqual(fixture.observations.map(({ method, request_path, query_present, credential_query_present }) => ({ method, request_path, query_present, credential_query_present })), [{ method: "POST", request_path: "/api/v1/auth/login", query_present: false, credential_query_present: false }]);
  assert.ok(fixture.observations[0].body_bytes > 0); assert.deepEqual(Object.keys(fixture.observations[0]).sort(), ["body_bytes", "credential_query_present", "method", "query_present", "request_path"]);
});
