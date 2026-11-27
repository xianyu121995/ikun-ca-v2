import React from "react";
import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { HackathonBoard } from "../app/hackathons/board.tsx";
import { chainLabel, EMPTY_COPY, groupEvents, LIST_PAGE_SIZE, LIST_PREVIEW, matchesChain, paintSnapshot, parseSnapshot, phaseAt, projectPage, recentPeriods, type HackathonEvent, type HackathonProject, type HackathonSnapshot } from "./hackathon-snapshot.ts";

const NOW = "2026-11-27T12:49:00Z";

function event(patch: Partial<HackathonEvent> = {}): HackathonEvent {
  return {
    id: "bnb-hackathon:sample",
    title: "示例黑客松",
    ecosystem: "bnb",
    classification: "hackathon",
    classification_reason: "标题写明黑客松。",
    summary: "",
    location: "线上",
    prize: "",
    official_status: null,
    phase: "live",
    phase_basis: "official_window",
    start_utc: "2026-11-01T00:00:00Z",
    end_utc: "2026-12-01T00:00:00Z",
    listed: true,
    missing_note: "",
    submission: { state: "not_published", note: "没有公布投稿。", form_url: null, projects: [] },
    results: { state: "not_published", note: "没有公布获奖。", projects: [] },
    milestones: [{ key: "window", label: "活动时间", display: "2026-11-01 08:00 至 2026-12-01 08:00 北京时间（UTC+8）", precision: "instant", source_url: "https://www.bnbchain.org/en/hackathons/sample", start_utc: "2026-11-01T00:00:00Z", end_utc: "2026-12-01T00:00:00Z" }],
    links: [{ label: "官方活动页", url: "https://www.bnbchain.org/en/hackathons/sample" }],
    ...patch,
  };
}

function snapshot(events: HackathonEvent[], changes: HackathonSnapshot["changes"] = []): HackathonSnapshot {
  return {
    schema: "hackathon-snapshot-v1",
    generated_at: NOW,
    generated_at_beijing: "2026-11-27 20:49",
    timezone: "Asia/Shanghai",
    standing: true,
    sources: [{ id: "bnb-hackathon-index", url: "https://www.bnbchain.org/en/hackathons", ok: true, checked_at: NOW, error: "", note: "" }],
    events,
    changes,
  };
}

test("a project without a source url is rejected instead of shown", () => {
  const value = snapshot([event({
    results: { state: "published", note: "x", projects: [{ name: "虚构", role: "winner", place: "", track: "", url: "", source_url: "", note: "" }] },
  })]);
  assert.equal(parseSnapshot(value), null);
  assert.equal(parseSnapshot({ ...snapshot([]), standing: false }), null);
});

test("ended events stay in the archive and an ended window moves there even if the file still says live", () => {
  const ended = event({ id: "old", title: "已结束的黑客松", official_status: "Ended", phase: "live" });
  const current = event({ id: "now", title: "进行中的黑客松" });
  const stale = event({ id: "stale", title: "文件还写着进行中", phase: "live", start_utc: "2026-01-01T00:00:00Z", end_utc: "2026-02-01T00:00:00Z" });
  const related = event({ id: "related", title: "Set and Earn", classification: "related", official_status: "Ended" });
  const groups = groupEvents([ended, current, stale, related], new Date(NOW));
  assert.deepEqual(groups.current.map(item => item.id), ["now"]);
  assert.deepEqual(groups.archive.map(item => item.id), ["old", "stale"]);
  assert.deepEqual(groups.relatedArchive.map(item => item.id), ["related"]);
  assert.equal(phaseAt(stale, new Date(NOW)), "ended");
});

test("empty submission and winner states stay empty on the page", () => {
  const html = renderToStaticMarkup(<HackathonBoard load={{ ok: true, snapshot: snapshot([event()]) }} now={NOW} />);
  assert.match(html, /黑客松监控/);
  assert.match(html, /第四期/);
  assert.match(html, /11\.1–12\.1/);
  assert.match(html, /<details class="hk-period" open="">/);
  assert.match(html, /北京时间（UTC\+8）/);
  assert.match(html, /没有公布投稿/);
  assert.match(html, /没有公布获奖/);
  assert.doesNotMatch(html, /这里看不到全部投稿|最近变化|长期核对|已结束（归档）/);
  assert.doesNotMatch(html, /没有可展示的项目/);
  assert.doesNotMatch(html, /虚构|示例队伍|冠军|官网|官推|>监控</);
  const listed = event({
    id: "listed",
    title: "有公开名单的黑客松",
    website: "https://example.com/hackathon",
    twitter: "https://x.com/examplehack",
    submission: {
      state: "published",
      note: "公开名单。",
      form_url: null,
      projects: [{
        name: "真实项目",
        role: "submitted",
        place: "",
        track: "DeFi",
        url: "https://example.com/project",
        source_url: "https://example.com/source",
        note: "SOL",
        info: "一句公开简介。",
        website: "https://example.com/project",
        twitter: "https://x.com/realproject",
      }],
    },
    results: {
      state: "published",
      note: "公开排名。",
      projects: [{
        name: "第一名项目",
        role: "winner",
        place: "第 1 名",
        track: "",
        url: "https://example.com/winner",
        source_url: "https://example.com/winner",
        note: "",
        website: "https://winner.example",
      }],
    },
  });
  const rich = renderToStaticMarkup(<HackathonBoard load={{ ok: true, snapshot: snapshot([listed]) }} now={NOW} />);
  assert.match(rich, /赛事官网/);
  assert.match(rich, /赛事官推/);
  assert.match(rich, /排名/);
  assert.match(rich, /<small>排名<\/small><strong>第 1 名<\/strong>/);
  assert.match(rich, /第 1 名/);
  assert.match(rich, /名单/);
  assert.match(rich, /一句公开简介/);
  assert.match(rich, /官网/);
  assert.match(rich, /@realproject 官推/);
  assert.match(rich, />监控</);
  assert.equal((rich.match(/>监控</g) ?? []).length, 1);
  assert.doesNotMatch(rich, /https:\/\/x\.com\/madeup|排名未公布/);
  assert.equal(parseSnapshot(snapshot([event({ website: "javascript:alert(1)" })])), null);
  assert.match(html, /第四期/);
  const missing = renderToStaticMarkup(<HackathonBoard load={{ ok: false, reason: "missing" }} now={NOW} />);
  assert.match(missing, new RegExp(EMPTY_COPY.missing.slice(0, 12)));
  assert.doesNotMatch(missing, /Agent ID|Bangkok/);
});

test("chain filter keeps BSC and SOL apart, including recent changes", () => {
  const bsc = event({ id: "bsc-event", title: "BSC 黑客松", ecosystem: "bnb", chain: "BSC" });
  const sol = event({ id: "sol-event", title: "SOL 黑客松", ecosystem: "solana", chain: "SOL" });
  assert.equal(matchesChain(bsc, "all"), true);
  assert.equal(matchesChain(bsc, "bsc"), true);
  assert.equal(matchesChain(bsc, "sol"), false);
  assert.equal(matchesChain(sol, "sol"), true);
  assert.equal(matchesChain(sol, "bsc"), false);
  assert.equal(matchesChain({ chain: "BSC, SOL", ecosystem: "both" }, "bsc"), true);
  assert.equal(matchesChain({ chain: "BSC, SOL", ecosystem: "both" }, "sol"), true);
  assert.equal(chainLabel(bsc), "BSC");
  assert.equal(chainLabel(sol), "SOL");
  assert.equal(chainLabel({ ecosystem: "solana" }), "SOL");
  assert.equal(matchesChain({ ecosystem: "unknown" }, "bsc"), false);
  assert.equal(matchesChain({ ecosystem: "unknown" }, "sol"), false);
  assert.equal(matchesChain({ ecosystem: "unknown" }, "all"), true);
  const html = renderToStaticMarkup(<HackathonBoard load={{ ok: true, snapshot: snapshot([bsc, sol], [
    { id: 1, kind: "gallery_opened", label: "有新名单", event: "BSC 黑客松", chain: "BSC", ecosystem: "bnb" },
    { id: 2, kind: "gallery_opened", label: "有新名单", event: "SOL 黑客松", chain: "SOL", ecosystem: "solana" },
  ]) }} now={NOW} />);
  assert.match(html, /按链筛选/);
  assert.match(html, /id="hk-chain-all"/);
  assert.match(html, /id="hk-chain-bsc"/);
  assert.match(html, /id="hk-chain-sol"/);
  assert.match(html, /data-ecosystem="bsc"/);
  assert.match(html, /data-ecosystem="sol"/);
  assert.match(html, /hk-chain-bsc/);
  assert.match(html, /hk-chain-sol/);
  assert.match(html, /BSC 黑客松/);
  assert.match(html, /SOL 黑客松/);
  assert.doesNotMatch(html, /链未标明|猜测/);
});

test("only the latest periods stay, as drawers, and undated events are left out", () => {
  const current = event({ id: "q4", title: "本季黑客松", start_utc: "2026-11-01T00:00:00Z", end_utc: "2026-12-01T00:00:00Z" });
  const summer = event({ id: "q3", title: "夏季黑客松", start_utc: "2026-07-02T00:00:00Z", end_utc: "2026-08-20T00:00:00Z" });
  const spring = event({ id: "q2", title: "春季黑客松", start_utc: "2026-04-03T00:00:00Z", end_utc: "2026-05-18T00:00:00Z" });
  const winter = event({ id: "q1", title: "太久远的黑客松", start_utc: "2026-02-01T00:00:00Z", end_utc: "2026-03-20T00:00:00Z" });
  const ancient = event({ id: "old", title: "2024 年旧榜", start_utc: "2024-01-01T00:00:00Z", end_utc: "2024-03-01T00:00:00Z" });
  const undated = event({ id: "none", title: "没有官方时间", start_utc: null, end_utc: null });
  const periods = recentPeriods([current, summer, spring, winter, ancient, undated], new Date(NOW));
  assert.deepEqual(periods.map(period => period.label), ["第四期", "第三期", "第二期"]);
  assert.equal(periods[0]?.range, "11.1–12.1");
  assert.equal(periods[2]?.range, "4.3–5.18");
  assert.equal(periods.some(period => period.events.some(item => item.title === "太久远的黑客松" || item.title === "2024 年旧榜" || item.title === "没有官方时间")), false);
  const early = recentPeriods([
    event({ id: "just", title: "刚开始", start_utc: "2026-10-02T00:00:00Z", end_utc: "2026-10-20T00:00:00Z" }),
    summer, spring, winter,
  ], new Date("2026-10-05T00:00:00Z"));
  assert.equal(early.length, 4);
  assert.equal(early.at(-1)?.range, "2.1–3.20");
  const html = renderToStaticMarkup(<HackathonBoard load={{ ok: true, snapshot: snapshot([current, summer, ancient, undated]) }} now={NOW} />);
  assert.match(html, /<details class="hk-period" open="">/);
  assert.match(html, /<details class="hk-period">/);
  assert.match(html, /本季黑客松/);
  assert.match(html, /夏季黑客松/);
  assert.doesNotMatch(html, /2024 年旧榜|没有官方时间/);
});

test("first paint keeps a short preview and later pages stay bounded", () => {
  const projects: HackathonProject[] = Array.from({ length: 120 }, (_, index) => ({
    name: `项目 ${index + 1}`,
    role: "submitted" as const,
    place: "",
    track: "",
    url: `https://example.com/p/${index + 1}`,
    source_url: `https://example.com/p/${index + 1}`,
    note: "",
  }));
  const full = snapshot([event({
    id: "worldsfair",
    title: "Crypto World's Fair",
    ecosystem: "solana",
    chain: "SOL",
    official_status: "awaiting_results",
    phase: "live",
    submission: { state: "published", note: "公开名单。", form_url: null, projects },
  })]);
  const painted = paintSnapshot(full, new Date(NOW));
  const shown = painted.events[0]!.submission;
  assert.equal(shown.project_total, 120);
  assert.equal(shown.projects.length, LIST_PREVIEW);
  assert.equal(shown.projects[0]!.name, "项目 1");
  assert.equal(shown.projects.at(-1)!.name, `项目 ${LIST_PREVIEW}`);
  const html = renderToStaticMarkup(<HackathonBoard load={{ ok: true, snapshot: painted }} now={NOW} />);
  assert.match(html, /共 120 个/);
  assert.match(html, /项目 1/);
  assert.match(html, /查看更多/);
  assert.equal(html.match(/class="hk-row"/g)?.length, LIST_PREVIEW);
  assert.doesNotMatch(html, /项目 21/);
  const page = projectPage(projects, 2, LIST_PAGE_SIZE);
  assert.equal(page.projects.length, LIST_PAGE_SIZE);
  assert.equal(page.projects[0]!.name, "项目 51");
  const focused = paintSnapshot(full, new Date(NOW), { eventId: "worldsfair", list: "submission", page: 2 });
  assert.equal(focused.events[0]!.submission.projects[0]!.name, "项目 51");
  assert.equal(focused.events[0]!.submission.projects.length, LIST_PAGE_SIZE);
  const paged = renderToStaticMarkup(<HackathonBoard load={{ ok: true, snapshot: focused }} now={NOW} focus={{ eventId: "worldsfair", list: "submission", page: 2 }} />);
  assert.match(paged, /项目 51/);
  assert.match(paged, /第 2 页，每页 50 个/);
  assert.match(paged, /上一页/);
  assert.match(paged, /下一页/);
  assert.equal(paged.match(/class="hk-row"/g)?.length, LIST_PAGE_SIZE);
  assert.doesNotMatch(paged, /项目 1</);
  const archived = paintSnapshot(snapshot([event({
    id: "old-list",
    title: "已结束名单",
    official_status: "completed",
    phase: "ended",
    submission: { state: "published", note: "公开名单。", form_url: null, projects },
  })]), new Date(NOW));
  assert.equal(archived.events[0]!.submission.project_total, 120);
  assert.equal(archived.events[0]!.submission.projects.length, 0);
});
