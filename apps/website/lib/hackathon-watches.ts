import { DatabaseSync } from "node:sqlite";
import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";

/** Hackathon tweet watches live only in this database. Hunter and tracking stores are never opened. */
const FORBIDDEN = /hackathon\.sqlite3|ikun-hackathon|tracking\.sqlite|hunter\.sqlite/i;

export interface HackathonWatch {
  id: string;
  handle: string;
  project_name: string;
  event_title: string;
  event_id: string;
  created_at: string;
  removed_at: string | null;
}

export interface HackathonTweet {
  id: string;
  watch_id: string;
  handle: string;
  project_name: string;
  tweet_id: string;
  text: string;
  url: string;
  occurred_at: string;
  fetched_at: string;
  removed: boolean;
}

export interface PublicTweet {
  tweet_id: string;
  text: string;
  url: string;
  occurred_at: string;
}

export function officialHandle(twitter?: string | null): string | null {
  if (!twitter) return null;
  try {
    const url = new URL(twitter);
    const host = url.hostname.replace(/^www\./, "");
    if (host !== "x.com" && host !== "twitter.com") return null;
    const handle = url.pathname.split("/").filter(Boolean)[0] ?? "";
    if (!/^[A-Za-z0-9_]{1,15}$/.test(handle)) return null;
    if (["intent", "share", "home", "search", "explore", "i", "hashtag", "compose"].includes(handle.toLowerCase())) return null;
    return handle;
  } catch {
    return null;
  }
}

export function hackathonWatchDbPath(env = process.env): string {
  const configured = env.IKUN_HACKATHON_WATCH_DB?.trim();
  const file = configured || path.join(process.cwd(), "var", "hackathon-watches", "watches.sqlite");
  if (FORBIDDEN.test(file)) throw new Error("黑客松推文库不能使用黑客松监控库或猎手/追踪库");
  return file;
}

function openDb(file = hackathonWatchDbPath()): DatabaseSync {
  mkdirSync(path.dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec(`
    CREATE TABLE IF NOT EXISTS watches (
      id TEXT PRIMARY KEY,
      handle TEXT NOT NULL,
      project_name TEXT NOT NULL,
      event_title TEXT NOT NULL,
      event_id TEXT NOT NULL,
      created_at TEXT NOT NULL,
      removed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS tweets (
      watch_id TEXT NOT NULL,
      tweet_id TEXT NOT NULL,
      text TEXT NOT NULL,
      url TEXT NOT NULL,
      occurred_at TEXT NOT NULL,
      fetched_at TEXT NOT NULL,
      PRIMARY KEY (watch_id, tweet_id)
    );
  `);
  return db;
}

export function listWatches(file = hackathonWatchDbPath()): HackathonWatch[] {
  const db = openDb(file);
  try {
    return db.prepare("SELECT id, handle, project_name, event_title, event_id, created_at, removed_at FROM watches ORDER BY created_at DESC").all() as HackathonWatch[];
  } finally {
    db.close();
  }
}

export function addWatch(input: { handle: string; project_name: string; event_title: string; event_id: string }, now = new Date(), file = hackathonWatchDbPath()): HackathonWatch {
  const handle = input.handle.trim().replace(/^@/, "");
  if (!/^[A-Za-z0-9_]{1,15}$/.test(handle)) throw new Error("官推账号无效");
  const project = input.project_name.trim();
  if (!project) throw new Error("缺少项目名");
  const db = openDb(file);
  try {
    const existing = db.prepare("SELECT id, removed_at FROM watches WHERE handle = ? COLLATE NOCASE AND removed_at IS NULL").get(handle) as { id: string } | undefined;
    if (existing) {
      return db.prepare("SELECT id, handle, project_name, event_title, event_id, created_at, removed_at FROM watches WHERE id = ?").get(existing.id) as HackathonWatch;
    }
    const row: HackathonWatch = {
      id: `hw_${now.getTime().toString(36)}_${handle.toLowerCase()}`,
      handle,
      project_name: project.slice(0, 160),
      event_title: input.event_title.trim().slice(0, 200),
      event_id: input.event_id.trim().slice(0, 300),
      created_at: now.toISOString(),
      removed_at: null,
    };
    db.prepare("INSERT INTO watches (id, handle, project_name, event_title, event_id, created_at, removed_at) VALUES (?, ?, ?, ?, ?, ?, NULL)").run(row.id, row.handle, row.project_name, row.event_title, row.event_id, row.created_at);
    return row;
  } finally {
    db.close();
  }
}

export function removeWatch(id: string, now = new Date(), file = hackathonWatchDbPath()): boolean {
  if (!/^hw_[A-Za-z0-9_]+$/.test(id)) return false;
  const db = openDb(file);
  try {
    const result = db.prepare("UPDATE watches SET removed_at = ? WHERE id = ? AND removed_at IS NULL").run(now.toISOString(), id);
    return result.changes > 0;
  } finally {
    db.close();
  }
}

export function listTweets(file = hackathonWatchDbPath()): HackathonTweet[] {
  const db = openDb(file);
  try {
    return db.prepare(`
      SELECT tweets.watch_id || ':' || tweets.tweet_id AS id, tweets.watch_id, watches.handle, watches.project_name,
             tweets.tweet_id, tweets.text, tweets.url, tweets.occurred_at, tweets.fetched_at,
             watches.removed_at IS NOT NULL AS removed
      FROM tweets JOIN watches ON watches.id = tweets.watch_id
      ORDER BY tweets.occurred_at DESC
    `).all() as HackathonTweet[];
  } finally {
    db.close();
  }
}

export function storeTweets(watch: HackathonWatch, tweets: PublicTweet[], fetchedAt = new Date(), file = hackathonWatchDbPath()): number {
  if (watch.removed_at) return 0;
  const db = openDb(file);
  let added = 0;
  try {
    const insert = db.prepare("INSERT OR IGNORE INTO tweets (watch_id, tweet_id, text, url, occurred_at, fetched_at) VALUES (?, ?, ?, ?, ?, ?)");
    const started = Date.parse(watch.created_at);
    for (const tweet of tweets) {
      const when = Date.parse(tweet.occurred_at);
      if (!Number.isFinite(when) || when < started) continue;
      if (!/^\d{5,25}$/.test(tweet.tweet_id) || !tweet.text.trim()) continue;
      if (tweet.url !== `https://x.com/${watch.handle}/status/${tweet.tweet_id}`) continue;
      const result = insert.run(watch.id, tweet.tweet_id, tweet.text.slice(0, 2000), tweet.url, new Date(when).toISOString(), fetchedAt.toISOString());
      added += result.changes;
    }
    return added;
  } finally {
    db.close();
  }
}

export function parseSyndication(body: string, handle: string): PublicTweet[] {
  const blobs = [body];
  const next = body.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (next?.[1]) blobs.push(next[1]);
  const found = new Map<string, PublicTweet>();
  for (const blob of blobs) {
    let parsed: unknown;
    try { parsed = JSON.parse(blob); } catch { continue; }
    walkTweets(parsed, handle, found);
  }
  return [...found.values()];
}

function walkTweets(value: unknown, handle: string, found: Map<string, PublicTweet>) {
  if (!value || typeof value !== "object") return;
  if (!Array.isArray(value)) {
    const row = value as { full_text?: unknown; text?: unknown; id_str?: unknown; id?: unknown; created_at?: unknown; user?: { screen_name?: unknown }; screen_name?: unknown };
    const text = typeof row.full_text === "string" ? row.full_text : typeof row.text === "string" ? row.text : "";
    const id = typeof row.id_str === "string" ? row.id_str : typeof row.id === "string" ? row.id : "";
    const user = typeof row.user?.screen_name === "string" ? row.user.screen_name : typeof row.screen_name === "string" ? row.screen_name : "";
    const when = typeof row.created_at === "string" ? Date.parse(row.created_at) : NaN;
    if (text.trim() && /^\d{5,25}$/.test(id) && user.toLowerCase() === handle.toLowerCase() && Number.isFinite(when)) {
      found.set(id, { tweet_id: id, text: text.trim(), url: `https://x.com/${handle}/status/${id}`, occurred_at: new Date(when).toISOString() });
    }
  }
  for (const child of Object.values(value as Record<string, unknown>)) walkTweets(child, handle, found);
}

export async function pullPublicTweets(handle: string): Promise<PublicTweet[]> {
  const response = await fetch(`https://syndication.twitter.com/srv/timeline-profile/screen-name/${encodeURIComponent(handle)}`, {
    headers: { "user-agent": "ikun-hackathon-watch/1.0", accept: "text/html,application/json" },
    signal: AbortSignal.timeout(4000),
  });
  if (!response.ok) return [];
  return parseSyndication(await response.text(), handle);
}

export async function refreshActiveWatches(file = hackathonWatchDbPath()): Promise<void> {
  if (process.env.IKUN_HACKATHON_WATCH_REFRESH === "0") return;
  const active = listWatches(file).filter(watch => !watch.removed_at).slice(0, 8);
  await Promise.all(active.map(async watch => {
    try {
      const tweets = await pullPublicTweets(watch.handle);
      storeTweets(watch, tweets, new Date(), file);
    } catch {
      // A failed read leaves the last stored tweets. Nothing is invented.
    }
  }));
}

export function teardownHackathonWatches(file = hackathonWatchDbPath()) {
  if (FORBIDDEN.test(file)) throw new Error("黑客松推文库不能使用黑客松监控库或猎手/追踪库");
  rmSync(file, { force: true });
  rmSync(`${file}-wal`, { force: true });
  rmSync(`${file}-shm`, { force: true });
}

export function beijingLabel(iso: string): string {
  const time = Date.parse(iso);
  if (!Number.isFinite(time)) return "";
  const formatted = new Intl.DateTimeFormat("zh-Hans-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(new Date(time));
  return `${formatted} 北京时间（UTC+8）`;
}
