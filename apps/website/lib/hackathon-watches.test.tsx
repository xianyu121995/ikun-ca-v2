import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { HackathonTweetBoard } from "../app/hackathon-tweets/board.tsx";
import { generateHackathonAnalysis, reviewAnalysis, reviewTweetEvent } from "./hackathon-analysis.ts";
import { orderByTimelineTime } from "./hackathon-watch-model.ts";
import { addWatch, hackathonWatchDbPath, listAnalyses, listHackathonTimeline, listNotes, listTweets, listWatches, officialHandle, parseSyndication, projectKey, removeWatch, saveAnalysis, saveNote, saveTweetEvent, storeTweets, teardownHackathonWatches, type HackathonTweet } from "./hackathon-watches.ts";

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

test("notes and analyses stay in the hackathon file and teardown leaves hunter data", () => {
  const { file, hunter } = tempDb();
  const key = projectKey("listed", "winner", "第一名项目");
  const saved = saveNote({ event_id: "listed", role: "winner", name: "第一名项目", text: "我的备注" }, new Date("2026-11-27T08:00:00Z"), file);
  assert.equal(saved?.text, "我的备注");
  assert.equal(listNotes(file)[key]?.text, "我的备注");
  assert.equal(saveNote({ event_id: "listed", role: "winner", name: "第一名项目", text: "  " }, new Date("2026-11-27T09:00:00Z"), file), null);
  assert.equal(listNotes(file)[key], undefined);
  saveAnalysis({ event_id: "listed", role: "winner", name: "第一名项目", text: "公开资料很少。", thin: true }, new Date("2026-11-27T10:00:00Z"), file);
  assert.equal(listAnalyses(file)[key]?.thin, true);
  teardownHackathonWatches(file);
  assert.equal(existsSync(file), false);
  assert.equal(readFileSync(hunter, "utf8"), "hunter-untouched");
});

test("analysis uses only the supplied evidence and refuses invented ranks", async () => {
  const evidence = { event_title: "有公开名单的黑客松", official_status: "live", name: "真实项目", role: "submitted", place: "", track: "", info: "一句公开简介。", website: "", handle: "", tweets: [] };
  assert.equal(reviewAnalysis(JSON.stringify({ analysis: "公开资料很少。项目名叫真实项目。", thin: true }), evidence)?.text.startsWith("公开资料很少"), true);
  assert.equal(reviewAnalysis(JSON.stringify({ analysis: "它是第 1 名。", thin: false }), evidence), null);
  assert.equal(reviewAnalysis(JSON.stringify({ analysis: "官网是 https://invented.example。", thin: false }), evidence), null);
  const missing = await generateHackathonAnalysis(evidence, { IKUN_AI_CONFIG: "/tmp/ikun-no-such-ai.json" } as NodeJS.ProcessEnv);
  assert.equal(missing.ok, false);
  if (!missing.ok) assert.match(missing.message, /不会编造分析/);
  const dir = mkdtempSync(path.join(tmpdir(), "hk-ai-"));
  const config = path.join(dir, "ai.json");
  writeFileSync(config, JSON.stringify({ provider: "deepseek", enabled: true, api_key: `sk-${"a".repeat(24)}` }));
  const generated = await generateHackathonAnalysis(evidence, { IKUN_AI_CONFIG: config } as NodeJS.ProcessEnv, async () => ({
    status: 200,
    json: async () => ({ choices: [{ message: { content: JSON.stringify({ analysis: "公开资料很少。简介只写了一句公开简介。", thin: true }) } }] }),
  }));
  assert.equal(generated.ok, true);
  if (generated.ok) assert.equal(generated.thin, true);
  const invented = await generateHackathonAnalysis(evidence, { IKUN_AI_CONFIG: config } as NodeJS.ProcessEnv, async () => ({
    status: 200,
    json: async () => ({ choices: [{ message: { content: JSON.stringify({ analysis: "公开资料显示它是冠军。", thin: false }) } }] }),
  }));
  assert.equal(invented.ok, false);
});

test("a dated hackathon tweet sits on the timeline by its Beijing time and leaves with the watch", () => {
  const rows = orderByTimelineTime([
    { source: "hunter", date: "2026-11-28", hour: "11" },
    { source: "hackathon", date: "2026-11-28", hour: "10" },
    { source: "hunter", date: "2026-11-28", hour: "09" },
  ]);
  assert.deepEqual(rows.map(row => row.source), ["hunter", "hackathon", "hunter"]);
  const reviewed = reviewTweetEvent(JSON.stringify({
    concrete: true, title: "开放交易", date: "2026-11-28", hour: "20", status: "confirmed", analysis: "推文写了明天 20:00 开放交易。",
  }), { text: "明天 20:00 开放交易", occurred_at: "2026-11-27T12:00:00Z", handle: "realproject", project_name: "真实项目" });
  assert.equal(reviewed?.thin, false);
  assert.equal(reviewed && !reviewed.thin ? reviewed.starts_at : "", "2026-11-28T12:00:00Z");
  assert.equal(reviewTweetEvent(JSON.stringify({
    concrete: true, title: "冠军", date: "2026-11-28", hour: "20", status: "confirmed", analysis: "它是第 1 名。",
  }), { text: "明天 20:00 开放交易", occurred_at: "2026-11-27T12:00:00Z", handle: "realproject", project_name: "真实项目" }), null);
  const { file, hunter } = tempDb();
  const watch = addWatch({ handle: "realproject", project_name: "真实项目", event_title: "有公开名单的黑客松", event_id: "listed" }, new Date("2026-11-27T00:00:00Z"), file);
  storeTweets(watch, [{ tweet_id: "1000000000000000002", text: "明天 20:00 开放交易", url: "https://x.com/realproject/status/1000000000000000002", occurred_at: "2026-11-27T12:00:00Z" }], new Date("2026-11-27T13:00:00Z"), file);
  saveTweetEvent({ watch_id: watch.id, tweet_id: "1000000000000000002", title: "开放交易", analysis: "推文写了明天 20:00 开放交易。", date: "2026-11-28", hour: "20", status: "confirmed", starts_at: "2026-11-28T12:00:00Z", thin: false }, new Date("2026-11-27T13:00:00Z"), file);
  const listed = listHackathonTimeline(file);
  assert.equal(listed.length, 1);
  assert.equal(listed[0]?.title, "开放交易");
  assert.ok(listed[0]?.entry_id.startsWith("hkt_"));
  assert.ok(listed[0]?.project_id.startsWith("hkp_"));
  assert.equal(removeWatch(watch.id, new Date("2026-11-27T14:00:00Z"), file), true);
  assert.equal(listHackathonTimeline(file).length, 0);
  assert.equal(readFileSync(hunter, "utf8"), "hunter-untouched");
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
    "lib/hackathon-watch-model.ts",
    "lib/hackathon-watches.ts",
    "app/api/hackathons/watches/route.ts",
    "app/api/hackathons/watches/[id]/route.ts",
    "app/hackathon-tweets/page.tsx",
    "app/hackathon-tweets/board.tsx",
    "app/hackathons/watch-button.tsx",
    "app/hackathons/project-tools.tsx",
    "app/api/hackathons/notes/route.ts",
    "app/api/hackathons/analyses/route.ts",
    "lib/hackathon-analysis.ts",
    "lib/hackathon-tweet-pass.ts",
    "app/api/hackathons/timeline/route.ts",
    "app/api/hackathons/timeline/[id]/route.ts",
  ];
  for (const file of files) {
    const source = readFileSync(path.join(root, file), "utf8");
    assert.doesNotMatch(source, /features\/tracking|features\/hunter|tracking-worker|hunter-worker|tracking\.sqlite|hunter\.sqlite/);
  }
  for (const file of ["app/hackathons/project-tools.tsx", "app/hackathons/watch-button.tsx", "app/hackathon-tweets/remove-watch.tsx", "components/projects-home.tsx"]) {
    const source = readFileSync(path.join(root, file), "utf8");
    assert.doesNotMatch(source, /hackathon-watches|node:fs|node:path|node:sqlite|node:child_process/);
  }
});
