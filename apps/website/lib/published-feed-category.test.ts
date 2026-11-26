import assert from "node:assert/strict";
import { test } from "node:test";
import { feedQuery } from "./published-feed";

const root = "http://127.0.0.1/api/v1/tracking/latest?profile=published-v1";
test("type filter is website-only and does not change the tracking query hash", () => {
  const plain = feedQuery(new URL(root + "&q=hello&ratings=S,A"));
  const typed = feedQuery(new URL(root + "&q=hello&ratings=S,A&category=" + encodeURIComponent("发射台")));
  assert.equal(typed.category, "发射台");
  assert.equal(plain.category, "all");
  assert.equal(typed.hash, plain.hash);
  assert.equal("category" in typed.query, false);
  assert.equal(feedQuery(new URL(root + "&category=none")).category, "none");
  for (const suffix of ["&category=DeFi", "&category=all&category=NFT"]) assert.throws(() => feedQuery(new URL(root + suffix)), suffix);
});
