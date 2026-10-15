import type { VoiceCandidate, VoiceMetadata, VoiceSession } from "./types.js";

export const VOICE_LIMITS = Object.freeze({ queue: 20, ttlMs: 30_000, metadataMs: 4_000, speechMs: 30_000, dedupe: 1024, dedupeMs: 600_000, subscriptions: 1000, notes: 4000 });
const uuid4 = "[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const activity = /^act_[0-9a-f]{8}-[0-9a-f]{4}-[45][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
export const isSubscriptionId = (value: unknown): value is string => typeof value === "string" && new RegExp(`^sub_${uuid4}$`).test(value);
const projectId = (value: unknown): value is string => typeof value === "string" && new RegExp(`^prj_${uuid4}$`).test(value);
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const positiveRevision = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value > 0;
const opaque = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 128 && !/[\s\u0000-\u001f\u007f]/u.test(value);
export function validSession(value: unknown): value is VoiceSession {
  return record(value) && opaque(value.user_id) && opaque(value.epoch) && (value.role === "user" || value.role === "superadmin");
}
export function candidateFromFrame(value: unknown): VoiceCandidate | null {
  if (!record(value) || value.type !== "tracking.feed.activity.created.v1" || value.delivery !== "live" || typeof value.event_id !== "string" || !new RegExp(`^evt_${uuid4}$`).test(value.event_id) || !record(value.data)) return null;
  const data = value.data;
  if (data.source !== "wss" || data.is_live_new !== true || data.replay !== false || (data.tweet_kind !== "original" && data.tweet_kind !== "quote") || typeof data.activity_id !== "string" || !activity.test(data.activity_id) || !isSubscriptionId(data.subscription_id) || !projectId(data.project_id) || typeof data.received_at !== "string") return null;
  const timestamp = data.received_at;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$/.test(timestamp)) return null;
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 19) !== timestamp.slice(0, 19)) return null;
  // Explicit projection: no text, handle, name, raw payload or event envelope is retained.
  return Object.freeze({ event_id: value.event_id, activity_id: data.activity_id, subscription_id: data.subscription_id, project_id: data.project_id, tweet_kind: data.tweet_kind, received_at: timestamp });
}
export function verifiedMetadata(value: unknown, candidate: VoiceCandidate): VoiceMetadata | null {
  if (!record(value) || value.subscription_id !== candidate.subscription_id || value.project_id !== candidate.project_id || !positiveRevision(value.subscription_revision) || !positiveRevision(value.project_revision) || !["S", "A", "B"].includes(value.rating as string) || typeof value.notes !== "string" || value.notes.length > VOICE_LIMITS.notes) return null;
  const notes = value.notes.replace(/\s+/gu, " ").trim();
  if (!notes || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/u.test(notes)) return null;
  return { subscription_id: candidate.subscription_id, project_id: candidate.project_id, notes, subscription_revision: value.subscription_revision as number, project_revision: value.project_revision as number, rating: value.rating as VoiceMetadata["rating"] };
}
const shanghai = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
function dayMs(now: number): number {
  const parts = shanghai.formatToParts(now);
  const part = (key: string) => Number(parts.find(p => p.type === key)?.value);
  return ((part("hour") * 60 + part("minute")) * 60 + part("second")) * 1000 + ((now % 1000) + 1000) % 1000;
}
export function isVoiceQuietHours(now: number): boolean {
  if (!Number.isFinite(now)) return true;
  const time = dayMs(now); return time >= 22 * 3600_000 || time < 8 * 3600_000;
}
export function nextVoiceBoundaryMs(now: number): number {
  const time = dayMs(now);
  return time < 8 * 3600_000 ? 8 * 3600_000 - time : time < 22 * 3600_000 ? 22 * 3600_000 - time : 32 * 3600_000 - time;
}
