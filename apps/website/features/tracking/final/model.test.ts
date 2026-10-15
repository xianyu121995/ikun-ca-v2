import assert from "node:assert/strict";
import { test } from "node:test";
import { createDemoData } from "./demo-data";
import { displayTime, emptyFilters, localMedia, paginate, relativeTime, selectPosts, statsFor, validateAccount, type AccountInput } from "./model";
const now = Date.parse("2026-10-15T00:30:00Z");
const seed = () => createDemoData(now);
test("approved fixture has ten S/A/B accounts and twelve explicitly fictitious posts", () => {
  const { accounts, posts } = seed();
  assert.equal(accounts.length, 10); assert.equal(posts.length, 12);
  assert.ok(posts.every(post => post.body.endsWith("(Demo post)")));
  assert.ok(accounts.every(account => account.ui_key.startsWith("demo-")));
  assert.deepEqual(statsFor(accounts, posts, now), { today: 7, S: 2, A: 3, B: 5, total: 10 });
});
test("posts are matched to current tracked accounts and sorted by publication descending", () => {
  const { accounts, posts } = seed(); const before = structuredClone(posts);
  const selected = selectPosts(accounts, [...posts].reverse(), emptyFilters, now);
  assert.equal(selected[0].ui_key, "demo-post-1"); assert.equal(selected[11].ui_key, "demo-post-12");
  assert.equal(selectPosts(accounts.slice(1), posts, emptyFilters, now).length, 10);
  assert.deepEqual(posts, before);
});
test("remark, project, handle including @, and body are searchable without case sensitivity", () => {
  const { accounts, posts } = seed();
  for (const query of ["主网上线", "HYPERLIQUID", "@HyperliquidX"]) assert.equal(selectPosts(accounts, posts, { ...emptyFilters, query }, now).length, 2);
  assert.equal(selectPosts(accounts, posts, { ...emptyFilters, query: "API rate limits" }, now).length, 1);
});
test("S/A/B and important filters combine", () => {
  const { accounts, posts } = seed();
  for (const [grade, count] of [["S", 3], ["A", 3], ["B", 6]] as const) assert.equal(selectPosts(accounts, posts, { ...emptyFilters, grade }, now).length, count);
  assert.equal(selectPosts(accounts, posts, { ...emptyFilters, grade: "S", important: true }, now).length, 2);
});
test("time windows use published time, rejecting unknown or future timestamps", () => {
  const { accounts, posts } = seed();
  assert.equal(selectPosts(accounts, posts, { ...emptyFilters, hours: "24" }, now).length, 9);
  assert.equal(selectPosts(accounts, posts, { ...emptyFilters, hours: "168" }, now).length, 12);
  const unknown = { ...posts[0], published_at: null }, future = { ...posts[0], published_at: new Date(now + 60000).toISOString() };
  assert.equal(selectPosts(accounts, [unknown, future], { ...emptyFilters, hours: "24" }, now).length, 0);
  assert.equal(selectPosts(accounts, [unknown, posts[0]], emptyFilters, now)[1].published_at, null);
});
test("six per page, clamped page after deletion, no fabricated empty pages", () => {
  const { posts } = seed(); assert.equal(paginate(posts, 1).items.length, 6); assert.equal(paginate(posts, 2).start, 7);
  assert.equal(paginate(posts.slice(0, 5), 2).page, 1); assert.equal(paginate([], 90).totalPages, 1);
  assert.equal(paginate([], 1).start, 0); assert.equal(paginate([], 1).end, 0);
});
test("today count follows Beijing day instead of UTC day", () => {
  const { accounts, posts } = seed(); assert.equal(statsFor(accounts, posts, now).today, 7);
  assert.match(displayTime(posts[2].published_at), /10\/15/);
});
test("add validates required fields, bounds, handle syntax and case-folded duplicates", () => {
  const { accounts } = seed(); const input: AccountInput = { handle: "@demo_project", name: "Demo", note: "关注测试网", grade: "A" };
  assert.equal(validateAccount(input, accounts), null);
  for (const handle of ["bad handle", "javascript:x", "x".repeat(16), ""]) assert.ok(validateAccount({ ...input, handle }, accounts));
  assert.ok(validateAccount({ ...input, handle: "@HYPERLIQUIDX" }, accounts));
  for (const patch of [{ name: " " }, { name: "x".repeat(51) }, { note: " " }, { note: "x".repeat(81) }]) assert.ok(validateAccount({ ...input, ...patch }, accounts));
});
test("removing an account hides its posts but does not destroy supplied history", () => {
  const { accounts, posts } = seed(); const remaining = accounts.filter(account => account.ui_key !== "demo-account-1");
  assert.equal(selectPosts(remaining, posts, emptyFilters, now).length, 10); assert.equal(posts.length, 12);
  assert.equal(statsFor(remaining, posts, now).total, 9);
});
test("unknown and future times remain explicit; unsafe or external media are not loaded", () => {
  assert.equal(relativeTime(null, now), "发布时间未知"); assert.equal(relativeTime(new Date(now + 60000).toISOString(), now), "时间待核实");
  assert.equal(localMedia("/tracking-prototype/demo.svg"), "/tracking-prototype/demo.svg");
  for (const src of ["javascript:alert(1)", "https://external.test/a.png", "//external.test/a.png", "/\\external.test/a.png"]) assert.equal(localMedia(src), null);
});
