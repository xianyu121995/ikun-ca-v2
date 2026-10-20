/** Trusted B1 session identity, supplied by the host. Never read identity from an SSE payload. */
export interface VoiceSession { user_id: string; epoch: string; role: "user" | "superadmin" }
export type VoiceIdentity = Pick<VoiceSession, "user_id" | "epoch">;
export interface VoiceCandidate {
  event_id: string; activity_id: string; subscription_id: string; project_id: string;
  tweet_kind: "original" | "quote"; received_at: string;
}
/** The existing controller supplies envelope.data and SSE lastEventId, without copying text/raw. */
export interface TrackingVoiceFrame { type: string; event_id: string; delivery: "live" | "history" | "replay" | "rest"; data: unknown }
/** Return only after both authenticated, successful reads and ID/revision checks. No feed-page fallback. */
export interface VoiceMetadata {
  subscription_id: string; project_id: string; project_name: string; subscription_revision: number;
  rating: "S" | "A" | "B"; project_revision: number;
}
export type ResolveVoiceMetadata = (candidate: Readonly<VoiceCandidate>, context: Readonly<VoiceSession> & { signal: AbortSignal }) => Promise<unknown>;
export type VoiceAvailability = "available" | "unsupported" | "no-local-voice";
export interface VoiceSpeechPort {
  availability(): VoiceAvailability;
  isUserGesture(event: Event): boolean;
  speak(text: string, hooks: { start(): void; end(): void; error(): void }): void;
  cancel(): void;
  observe?(listener: () => void): () => void;
}
export interface VoiceStorage { getItem(key: string): string | null; setItem(key: string, value: string): void }
export interface VoiceClock { now(): number; setTimeout(callback: () => void, ms: number): unknown; clearTimeout(handle: unknown): void }
export type VoiceStatus = "signed-out" | "unsupported" | "no-local-voice" | "off" | "locked" | "disconnected" | "quiet-hours" | "ready" | "resolving" | "starting" | "speaking" | "failed";
export interface VoiceSnapshot {
  status: VoiceStatus; enabled: boolean; armed: boolean; connected: boolean; available: VoiceAvailability;
  queued: number; disabled_subscription_ids: readonly string[]; storage_available: boolean; quiet_hours: { enabled: boolean; start: number; end: number };
}
export interface VoiceOptions { speech: VoiceSpeechPort; resolveMetadata: ResolveVoiceMetadata; storage?: VoiceStorage; clock?: VoiceClock }
