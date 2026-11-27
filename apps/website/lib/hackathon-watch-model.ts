/** Client-safe hackathon watch types and pure helpers. No Node or sqlite imports. */

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

export interface StoredNote {
  text: string;
  updated_at: string;
}

export interface StoredAnalysis {
  text: string;
  thin: boolean;
  generated_at: string;
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

export function projectKey(eventId: string, role: string, name: string) {
  return `${eventId}\u001f${role}\u001f${name}`;
}

export function beijingLabel(iso: string): string {
  const time = Date.parse(iso);
  if (!Number.isFinite(time)) return "";
  const formatted = new Intl.DateTimeFormat("zh-Hans-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(new Date(time));
  return `${formatted} 北京时间（UTC+8）`;
}
