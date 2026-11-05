import assert from "node:assert/strict";
import { test } from "node:test";
import { countIntendedMonitors, visibleMonitors } from "../../lib/tracking-monitor-count.ts";

const row = (desired_state: string, operation_state: string, observed_state: string) => ({ desired_state, operation_state, observed_state });

test("monitor count ignores removed intent, including stale observations", () => {
  const rows = [
    ...Array.from({ length: 107 }, () => row("running", "succeeded", "running")),
    ...Array.from({ length: 142 }, () => row("removed", "succeeded", "unknown")),
  ];
  assert.equal(rows.length, 249);
  assert.equal(countIntendedMonitors(rows), 107);
  assert.equal(visibleMonitors(rows).length, 107);
});

test("completed removals stay hidden when observation is no longer absent", () => {
  const removed = [
    row("removed", "succeeded", "absent"),
    row("removed", "succeeded", "unknown"),
    row("removed", "succeeded", "running"),
  ];
  assert.equal(countIntendedMonitors(removed), 0);
  assert.deepEqual(visibleMonitors(removed), []);
});

test("in-progress removals stay on the list but are not active monitors", () => {
  const rows = [
    row("running", "succeeded", "running"),
    row("stopped", "succeeded", "absent"),
    row("removed", "running", "unknown"),
    row("removed", "accepted", "unknown"),
    row("removed", "unknown", "absent"),
    row("removed", "failed", "unknown"),
  ];
  assert.equal(countIntendedMonitors(rows), 2);
  assert.equal(visibleMonitors(rows).length, 6);
  assert.ok(visibleMonitors(rows).every(item => !(item.desired_state === "removed" && item.operation_state === "succeeded")));
});
