import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { HackathonTweetBoard } from "../app/hackathon-tweets/board.tsx";
import { addWatch, hackathonWatchDbPath, listTweets, listWatches, officialHandle, parseSyndication, removeWatch, storeTweets, teardownHackathonWatches, type HackathonTweet } from "./hackathon-watches.ts";

function tempDb() {
  const dir = mkdtempSync(path.join(tmpdir(), "hk-watch-"));
  const file = path.join(dir, "watches.sqlite");
  const hunter = path.join(dir, "hunter.sqlite");
  writeFileSync(hunter, "hunter-untouched");
  return { file, hunter };
}

test("official handles come only from an x or twitter profile url", () => {
  assert.equal(officialHandle("https://x.com/realproject"), "realproject");
  assert.equal(officialHandle("https://twitter.com/Real_Name"), "Real_Name");
  assert.equal(officialHandle("https://x.com/realproject/status/1"), "realproject");
  assert.equal(officialHandle(""), null);
  assert.equal(officialHandle("https://example.com/@notreally"), null);
  assert.equal(officialHandle("not a handle"), null);
  assert.equal(officialHandle("https://x.com/intent/tweet"), null);
});

test("watches and tweets stay in the hackathon file and a stopped watch takes no newer tweets", () => {
  const { file, hunter } = tempDb();
  const started = new Date("2026-11-27T00:00:00Z");
  const watch = addWatch({ handle: "realproject", project_name: "真实项目", event_title: "有公开名单的黑客松", event_id: "listed" }, started, file);
  assert.equal(addWatch({ handle: "@realproject", project_name: "重复", event_title: "", event_id: "" }, started, file).id, watch.id);
  const older = { tweet_id: "1000000000000000001", text: "监控开始前", url: "https://x.com/realproject/status/1000000000000000001", occurred_at: "2026-11-26T00:00:00Z" };
  const newer = { tweet_id: "1000000000000000002", text: "公开新推文", url: "https://x.com/realproject/status/1000000000000000002", occurred_at: "2026-11-27T08:00:00Z" };
  const forged = { ...newer, tweet_id: "1000000000000000003", url: "https://x.com/someone/status/1000000000000000003" };
  assert.equal(storeTweets(watch, [older, newer, forged], new Date("2026-11-27T09:00:00Z"), file), 1);
  assert.equal(listTweets(file).map(tweet => tweet.text).join(","), "公开新推文");
  assert.equal(removeWatch(watch.id, new Date("2026-11-27T10:00:00Z"), file), true);
  const stopped = listWatches(file)[0]!;
  assert.ok(stopped.removed_at);
  assert.equal(storeTweets(stopped, [{ tweet_id: "1000000000000000004", text: "停止后", url: "https://x.com/realproject/status/1000000000000000004", occurred_at: "2026-11-27T11:00:00Z" }], new Date("2026-11-27T12:00:00Z"), file), 0);
  assert.equal(listTweets(file).length, 1);
  assert.equal(readFileSync(hunter, "utf8"), "hunter-untouched");
  teardownHackathonWatches(file);
  assert.equal(existsSync(file), false);
  assert.equal(existsSync(`${file}-wal`), false);
  assert.equal(readFileSync(hunter, "utf8"), "hunter-untouched");
});

test("the watch database refuses the monitor and hunter filenames", () => {
  assert.throws(() => hackathonWatchDbPath({ IKUN_HACKATHON_WATCH_DB: "/var/lib/ikun-hackathon/hackathon.sqlite3" }));
  assert.throws(() => hackathonWatchDbPath({ IKUN_HACKATHON_WATCH_DB: "/var/lib/tracking.sqlite" }));
});

test("syndication text is stored only when the account and timestamp are present", () => {
  const body = JSON.stringify({
    tweets: [
      { id_str: "2000000000000000001", full_text: "真实推文", created_at: "Fri Nov 27 08:00:00 +0000 2026", user: { screen_name: "realproject" } },
      { id_str: "2000000000000000002", full_text: "别人的推文", created_at: "Fri Nov 27 08:00:00 +0000 2026", user: { screen_name: "other" } },
      { full_text: "没有编号", created_at: "Fri Nov 27 08:00:00 +0000 2026", user: { screen_name: "realproject" } },
    ],
  });
  const parsed = parseSyndication(body, "realproject");
  assert.deepEqual(parsed.map(tweet => tweet.text), ["真实推文"]);
  assert.equal(parsed[0]?.url, "https://x.com/realproject/status/2000000000000000001");
  assert.deepEqual(parseSyndication("not json", "realproject"), []);
});

test("the tweet page lists a watched account and can delete it without showing hunter tracking", () => {
  const html = renderToStaticMarkup(<HackathonTweetBoard watches={[{
    id: "hw_test_realproject", handle: "realproject", project_name: "真实项目", event_title: "有公开名单的黑客松", event_id: "listed", created_at: "2026-11-27T00:00:00Z", removed_at: null,
  }]} tweets={[]} csrf="csrf" />);
  assert.match(html, /黑客松推文监控/);
  assert.match(html, /@realproject/);
  assert.match(html, />删除</);
  assert.match(html, /还没有读到新推文/);
  assert.match(html, /北京时间（UTC\+8）/);
  assert.doesNotMatch(html, /href="\/hunter|href="\/tracking/);
  const kept: HackathonTweet = { id: "hw_test_realproject:2000000000000000001", watch_id: "hw_test_realproject", handle: "realproject", project_name: "真实项目", tweet_id: "2000000000000000001", text: "公开新推文", url: "https://x.com/realproject/status/2000000000000000001", occurred_at: "2026-11-27T08:00:00Z", fetched_at: "2026-11-27T09:00:00Z", removed: true };
  const stopped = renderToStaticMarkup(<HackathonTweetBoard watches={[]} tweets={[kept]} />);
  assert.match(stopped, /已停止监控/);
  assert.match(stopped, /公开新推文/);
});

test("hackathon watch code does not import hunter or tracking", () => {
  const root = path.resolve(import.meta.dirname, "..");
  const files = [
    "lib/hackathon-watches.ts",
    "app/api/hackathons/watches/route.ts",
    "app/api/hackathons/watches/[id]/route.ts",
    "app/hackathon-tweets/page.tsx",
    "app/hackathon-tweets/board.tsx",
    "app/hackathons/watch-button.tsx",
  ];
  for (const file of files) {
    const source = readFileSync(path.join(root, file), "utf8");
    assert.doesNotMatch(source, /features\/tracking|features\/hunter|tracking-worker|hunter-worker|tracking\.sqlite|hunter\.sqlite/);
  }
});
