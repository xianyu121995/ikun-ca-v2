import type { VoiceStorage } from "./types.js";
import { DEFAULT_QUIET_HOURS, isSubscriptionId, validHour, VOICE_LIMITS, type VoiceQuietHours } from "./validation.js";

export interface VoicePreferences { enabled: boolean; disabled: Set<string>; quiet: VoiceQuietHours }
export const voicePreferenceKey = (userId: string) => `ikun.voice.v1.${encodeURIComponent(userId)}`;
export function loadVoicePreferences(storage: VoiceStorage | undefined, userId: string): { preferences: VoicePreferences; available: boolean } {
  const empty = (): VoicePreferences => ({ enabled: false, disabled: new Set(), quiet: { ...DEFAULT_QUIET_HOURS } });
  if (!storage) return { preferences: empty(), available: false };
  try {
    const raw = storage.getItem(voicePreferenceKey(userId));
    if (raw === null) return { preferences: empty(), available: true };
    if (raw.length > 65_536) return { preferences: empty(), available: true };
    const data: unknown = JSON.parse(raw);
    if (!data || typeof data !== "object") return { preferences: empty(), available: true };
    const v = data as Record<string, unknown>;
    if (v.version !== 1 || typeof v.enabled !== "boolean" || !Array.isArray(v.disabled_subscription_ids) || v.disabled_subscription_ids.length > VOICE_LIMITS.subscriptions || !v.disabled_subscription_ids.every(isSubscriptionId)) return { preferences: empty(), available: true };
    const q = v.quiet_hours as Record<string, unknown> | undefined;
    const quiet = q && typeof q === "object" && typeof q.enabled === "boolean" && validHour(q.start) && validHour(q.end) ? { enabled: q.enabled, start: q.start, end: q.end } : { ...DEFAULT_QUIET_HOURS };
    return { preferences: { enabled: v.enabled, disabled: new Set(v.disabled_subscription_ids), quiet }, available: true };
  } catch { return { preferences: empty(), available: false }; }
}
export function saveVoicePreferences(storage: VoiceStorage | undefined, userId: string, preferences: VoicePreferences): boolean {
  try {
    if (!storage) return false;
    storage.setItem(voicePreferenceKey(userId), JSON.stringify({ version: 1, enabled: preferences.enabled, disabled_subscription_ids: [...preferences.disabled], quiet_hours: preferences.quiet }));
    return true;
  } catch { return false; }
}
export function browserVoiceStorage(): VoiceStorage | undefined {
  try { return typeof window === "undefined" ? undefined : window.localStorage; } catch { return undefined; }
}
