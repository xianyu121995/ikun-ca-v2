import { test } from "node:test";
import assert from "node:assert/strict";
import { demoActivities, demoProject, demoSubscriptions, fixtureCommandId, fixtureTime, projectIds, subscriptionIds } from "./demo-fixtures";
import { activityTime, canWrite, isUnverified, mutationBlock, operationLabel, primaryOperation, projectRows, publicError, safeTweetURL, toAction, trackingActivities, validateAdd, validateReceipt, validProjectId, validSubscriptionId } from "./view-model";
import type { CommandDTO, SubscriptionDTO } from "./types";
test("canonical and subscription IDs remain separate, no handle identity", () => {
  assert.ok(validProjectId(projectIds[0])); assert.ok(validSubscriptionId(subscriptionIds[0]));
  assert.equal(validProjectId(subscriptionIds[0]), false); assert.equal(validSubscriptionId(projectIds[0]), false);
  assert.equal(validProjectId("demo_meridian"), false);
});
test("management defaults false and role/capability must both allow", () => {
  assert.equal(canWrite({}), false); assert.equal(canWrite({ role: "superadmin" }), false);
  assert.equal(canWrite({ role: "user", capabilities: { can_manage_tracking: true } }), false);
  assert.equal(canWrite({ role: "superadmin", capabilities: { can_manage_tracking: true } }), true);
});
test("connected ACK cannot become completed/running", () => {
  const row = demoSubscriptions()[1]; assert.equal(row.connection, "connected"); assert.equal(row.operation_state, "accepted"); assert.equal(row.observed_state, "stopped");
  assert.match(mutationBlock(row)!, /等待业务完成/); assert.equal(projectRows([row], "", "running", "latest").length, 0);
});
test("pending, unknown and unknown observed states block mutations", () => {
  for (const state of ["accepted", "pending", "running", "unknown"] as const) assert.ok(mutationBlock({ ...demoSubscriptions()[0], operation_state: state }));
  assert.ok(mutationBlock({ ...demoSubscriptions()[0], observed_state: "unknown" }));
  assert.equal(mutationBlock(demoSubscriptions()[0]), null);
});
test("unrelated revision changes cannot clear an unknown write without receipt query", () => {
  const updated = { ...demoSubscriptions()[0], revision: 10 };
  assert.equal(isUnverified(updated, { revision: 3, queried: false }), true);
  assert.equal(isUnverified(updated, { revision: 3, queried: true }), false);
  assert.equal(isUnverified({ ...updated, observed_state: "unknown" }, { revision: 3, queried: true }), true);
  assert.equal(isUnverified(updated, { revision: 10, queried: true }), true);
});
test("callbacks carry subscription ID and revision without changing project or home", () => {
  const before = demoSubscriptions()[0], copy = structuredClone(before);
  assert.deepEqual(toAction(before, "remove"), { subscription_id: subscriptionIds[0], project_id: projectIds[0], operation: "remove", revision: 3 });
  assert.deepEqual(before, copy); assert.equal("home_membership" in toAction(before, "remove"), false);
});
test("stable removal leaves tombstone out of default projection", () => {
  const rows = demoSubscriptions(); assert.equal(projectRows(rows, "", "all", "latest").length, 7);
  assert.equal(projectRows(rows, "", "all", "latest", true).length, 8);
});
test("search, filters and sorting are pure and include canonical references", () => {
  const rows = demoSubscriptions(), before = structuredClone(rows);
  assert.equal(projectRows(rows, subscriptionIds[0], "all", "name")[0].project_id, projectIds[0]);
  assert.equal(projectRows(rows, "@demo_axiom".slice(1), "pending", "name").length, 1);
  assert.equal(projectRows(rows, "", "all", "name")[0].name, "Axiom Network"); assert.deepEqual(rows, before);
});
test("add requires registered project and explicit confirmation, no invented ID", () => {
  const input = { ...demoProject, x_user_id: null, notes: "", confirmed: true as const };
  assert.equal(validateAdd(input), null);
  assert.match(validateAdd({ ...input, project_id: "new-demo" })!, /canonical/);
  assert.match(validateAdd({ ...input, confirmed: false as unknown as true })!, /确认/);
  assert.ok(validateAdd({ ...input, name: "x".repeat(121) }));
  assert.ok(validateAdd({ ...input, x_handle: "@demo" }));
});
test("canonical pending command may have null references without placeholders", () => {
  const command: CommandDTO = { command_id: fixtureCommandId, state: "pending", project_id: null, subscription_id: null, revision: null, updated_at: fixtureTime, error_code: null, request_id: "demo-1" };
  assert.equal(validateReceipt(command), true);
  assert.equal(validateReceipt(command, demoSubscriptions()[0]), false);
  assert.equal(validateReceipt({ ...command, command_id: "demo-id" }), false);
});
test("unknown occurrence uses received time and retains unknown label", () => {
  assert.deepEqual(activityTime(demoActivities()[1]), { at: "2026-10-14T23:50:00.000Z", receivedOnly: true });
  assert.equal(activityTime(demoActivities()[0]).receivedOnly, false);
});
test("safe links require exact X HTTPS tweet paths and no credentials", () => {
  assert.ok(safeTweetURL("https://x.com/demo/status/123"));
  for (const url of ["javascript:alert(1)", "https://x.com.evil.test/demo/status/1", "http://x.com/demo/status/1", "https://user:pass@x.com/demo/status/1", "https://x.com:999/demo/status/1"]) assert.equal(safeTweetURL(url), null);
});
test("raw thrown errors are not exposed; public error keeps request ID", () => {
  assert.equal(publicError(new Error("private provider URL and secret")).message.includes("private"), false);
  assert.equal(publicError({ code: "VERSION_CONFLICT", message: "公开错误", request_id: "public-1" }).request_id, "public-1");
});
test("DTO view projection has exact subscription fields and no home/hunter details", () => {
  const row: SubscriptionDTO = demoSubscriptions()[0];
  assert.deepEqual(Object.keys(row).sort(), ["subscription_id", "project_id", "name", "x_user_id", "x_handle", "notes", "revision", "desired_state", "observed_state", "operation_state", "connection", "last_tweet_at", "created_at", "updated_at"].sort());
  assert.equal(row.x_user_id, null);
});
test("absent, running and stopped observations expose start, stop and resume callbacks", () => {
  const rows = demoSubscriptions();
  assert.equal(primaryOperation(rows[7]), "start"); assert.equal(operationLabel(primaryOperation(rows[7])), "启动");
  assert.equal(primaryOperation(rows[0]), "stop"); assert.equal(primaryOperation(rows[3]), "resume");
});
test("tweet feed rejects unrelated and mismatched subscriptions, retaining stopped history", () => {
  const rows = demoSubscriptions(), tweets = demoActivities(), before = structuredClone(tweets);
  const outside = { ...tweets[0], subscription_id: subscriptionIds[7] };
  const mismatched = { ...tweets[0], project_id: projectIds[1] };
  assert.equal(trackingActivities([...tweets, outside, mismatched], rows).length, tweets.length);
  assert.equal(trackingActivities(tweets, rows, projectIds[3]).length, 1);
  assert.deepEqual(tweets, before);
});
test("tweet filters combine project, text, Beijing date and chronological ordering", () => {
  const rows = demoSubscriptions(), tweets = demoActivities();
  assert.equal(trackingActivities(tweets, rows, projectIds[0]).length, 2);
  assert.equal(trackingActivities(tweets, rows, projectIds[0], "", "oldest")[0].activity_id, "fixture-activity-6");
  assert.equal(trackingActivities(tweets, rows, projectIds[0], "testnet", "latest", "2026-10-15").length, 1);
  assert.equal(trackingActivities(tweets, rows, projectIds[0], "testnet", "latest", "2026-10-14").length, 0);
  assert.equal(trackingActivities([{ ...tweets[0], occurred_at: "invalid" }], rows, "all", "", "latest", "2026-10-15").length, 0);
});
