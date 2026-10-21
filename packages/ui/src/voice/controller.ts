import type { VoiceCandidate, VoiceClock, VoiceIdentity, VoiceOptions, VoiceSession, VoiceSnapshot, VoiceStatus } from "./types.js";
import { candidateFromFrame, DEFAULT_QUIET_HOURS, isSubscriptionId, isVoiceQuietHours, nextVoiceBoundaryMs, validHour, validSession, verifiedMetadata, VOICE_LIMITS, type VoiceQuietHours } from "./validation.js";
import { loadVoicePreferences, saveVoicePreferences, voicePreferenceKey, type VoicePreferences } from "./preferences.js";

const systemClock: VoiceClock = { now: Date.now, monotonic: () => performance.now(), setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: handle => clearTimeout(handle as ReturnType<typeof setTimeout>) };
interface Pending { candidate: VoiceCandidate; expires: number }
interface Job extends Pending { generation: number; abort: AbortController; timer: unknown; phase: "resolving" | "starting" | "speaking" }

/** One instance per logged-in browser page. It never creates a feed, fetches metadata or stores event data. */
export class TrackingVoiceController {
  private readonly clock: VoiceClock;
  private session: VoiceSession | null = null;
  private preferences: VoicePreferences = { enabled: false, disabled: new Set(), quiet: { ...DEFAULT_QUIET_HOURS } };
  private storageAvailable = true;
  private armed = false;
  private activatedInSession = false;
  private connected = false;
  private failed = false;
  private disposed = false;
  private generation = 0;
  private notBefore = Infinity;
  private highWater = -Infinity;
  private elapsedHighWater = -Infinity;
  private queue: Pending[] = [];
  private active: Job | undefined;
  private timer: unknown;
  private readonly events = new Map<string, number>();
  private readonly activities = new Map<string, number>();
  private readonly listeners = new Set<() => void>();
  private stopObserving: (() => void) | undefined;
  private snapshot: VoiceSnapshot;

  constructor(private readonly options: VoiceOptions) {
    this.clock = options.clock ?? systemClock;
    this.snapshot = this.makeSnapshot();
    try {
      this.stopObserving = options.speech.observe?.(() => {
        if (this.availability() !== "available") { this.armed = false; this.activatedInSession = false; this.dropAll(); }
        this.tick();
      });
    } catch { /* An optional capability observer must not break the existing feed. */ }
  }
  readonly getSnapshot = (): VoiceSnapshot => this.snapshot;
  readonly subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  preferenceKey(): string | null { return this.session ? voicePreferenceKey(this.session.user_id) : null; }
  private now(): number {
    const value = this.clock.now();
    if (!Number.isFinite(value)) return Infinity;
    // Calendar time is used only for quiet hours; rollback must not reopen their boundary.
    this.highWater = Math.max(this.highWater, value); return this.highWater;
  }
  private elapsed(): number {
    const value = this.clock.monotonic?.() ?? this.clock.now();
    if (!Number.isFinite(value)) return Infinity;
    this.elapsedHighWater = Math.max(this.elapsedHighWater, value); return this.elapsedHighWater;
  }
  private availability() { try { return this.options.speech.availability(); } catch { return "unsupported" as const; } }
  private same(identity: VoiceIdentity): boolean { return !!this.session && identity.user_id === this.session.user_id && identity.epoch === this.session.epoch; }
  private permitted(now: number): boolean {
    return !this.disposed && !!this.session && this.preferences.enabled && this.armed && this.connected && !this.failed && this.availability() === "available" && !isVoiceQuietHours(now, this.preferences.quiet);
  }
  private status(): VoiceStatus {
    if (!this.session || this.disposed) return "signed-out";
    const capability = this.availability(); if (capability !== "available") return capability;
    if (this.failed) return "failed";
    if (!this.preferences.enabled) return "off";
    if (!this.connected) return "disconnected";
    if (!this.armed) return "locked";
    if (isVoiceQuietHours(this.now(), this.preferences.quiet)) return "quiet-hours";
    return this.active?.phase ?? "ready";
  }
  private makeSnapshot(): VoiceSnapshot {
    return Object.freeze({ status: this.status(), enabled: this.preferences.enabled, armed: this.armed, connected: this.connected, available: this.availability(), queued: this.queue.length + (this.active ? 1 : 0), disabled_subscription_ids: Object.freeze([...this.preferences.disabled]), storage_available: this.storageAvailable , quiet_hours: Object.freeze({ ...this.preferences.quiet })});
  }
  private publish(): void {
    const value = this.makeSnapshot(); if (JSON.stringify(value) === JSON.stringify(this.snapshot)) return;
    this.snapshot = value;
    for (const listener of this.listeners) { try { listener(); } catch { /* A view failure cannot interrupt the existing feed. */ } }
  }
  private dropAll(): void {
    this.generation++; this.queue = [];
    const previous = this.active; this.active = undefined;
    if (previous) { previous.abort.abort(); this.clock.clearTimeout(previous.timer); }
    this.clock.clearTimeout(this.timer); this.timer = undefined;
    try { this.options.speech.cancel(); } catch { /* Stop is best effort; never retry speaking. */ }
  }
  private persist(): void { if (this.session) this.storageAvailable = saveVoicePreferences(this.options.storage, this.session.user_id, this.preferences); }

  setSession(session: VoiceSession | null): void {
    if (this.disposed) return;
    const next = validSession(session) ? Object.freeze({ user_id: session.user_id, epoch: session.epoch, role: session.role }) : null;
    if (next && this.session && this.same(next) && next.role === this.session.role) return;
    this.dropAll(); this.session = next; this.armed = false; this.activatedInSession = false; this.connected = false; this.failed = false; this.notBefore = Infinity;
    this.events.clear(); this.activities.clear();
    const loaded = next ? loadVoicePreferences(this.options.storage, next.user_id) : null;
    this.preferences = loaded?.preferences ?? { enabled: false, disabled: new Set(), quiet: { ...DEFAULT_QUIET_HOURS } };
    this.storageAvailable = loaded?.available ?? !!this.options.storage;
    this.publish();
  }
  setStreamConnected(connected: boolean, identity: VoiceIdentity): void {
    if (this.disposed || !this.same(identity) || this.connected === connected) return;
    this.dropAll(); this.connected = connected; this.notBefore = this.elapsed();
    if (!connected) this.armed = false;
    this.tick();
  }
  /** Resume only this page's previous trusted activation after a transport reconnect. No persisted preference can unlock it. */
  resumeAfterReconnect(identity: VoiceIdentity, hasBeenActive: boolean): boolean {
    if (this.disposed || !this.same(identity) || hasBeenActive !== true || !this.activatedInSession ||
        !this.connected || !this.preferences.enabled || this.failed || this.availability() !== "available") return false;
    this.armed = true; this.tick(); return true;
  }
  /** Call synchronously from a trusted click/keyboard gesture, never from an effect or persisted preference. */
  enableFromGesture(event: Event): boolean {
    if (this.disposed || !this.session || this.availability() !== "available") { this.publish(); return false; }
    let gesture = false; try { gesture = this.options.speech.isUserGesture(event); } catch { /* Fail closed. */ }
    if (!gesture) { this.failed = true; this.armed = false; this.activatedInSession = false; this.dropAll(); this.publish(); return false; }
    this.dropAll(); this.preferences.enabled = true; this.armed = true; this.activatedInSession = true; this.failed = false; this.notBefore = this.elapsed(); this.persist(); this.tick(); return true;
  }
  disable(): void {
    if (this.disposed) return;
    this.preferences.enabled = false; this.armed = false; this.activatedInSession = false; this.failed = false; this.dropAll(); this.persist(); this.publish();
  }
  setSubscriptionEnabled(subscriptionId: string, enabled: boolean): boolean {
    if (this.disposed || !this.session || !isSubscriptionId(subscriptionId)) return false;
    if (!enabled && !this.preferences.disabled.has(subscriptionId) && this.preferences.disabled.size >= VOICE_LIMITS.subscriptions) return false;
    if (enabled) this.preferences.disabled.delete(subscriptionId); else this.preferences.disabled.add(subscriptionId);
    // Cancels an in-flight metadata read as well as a speaking item; late answers cannot restart it.
    this.dropAll(); this.notBefore = this.elapsed(); this.persist(); this.tick(); return true;
  }
  reloadPreferences(): void {
    if (!this.session || this.disposed) return;
    const loaded = loadVoicePreferences(this.options.storage, this.session.user_id);
    this.dropAll(); this.armed = false; this.activatedInSession = false; this.preferences = loaded.preferences; this.storageAvailable = loaded.available; this.publish();
  }
  suspend(): void {
    this.armed = false; this.activatedInSession = false; this.connected = false; this.notBefore = this.elapsed(); this.dropAll(); this.publish();
  }
  private remember(candidate: VoiceCandidate, now: number): boolean {
    for (const map of [this.events, this.activities]) for (const [id, until] of map) if (until <= now) map.delete(id);
    if (this.events.has(candidate.event_id) || this.activities.has(candidate.activity_id)) return false;
    // Never evict an unexpired ID just to make room; overload drops new work rather than replaying old work.
    if (this.events.size >= VOICE_LIMITS.dedupe || this.activities.size >= VOICE_LIMITS.dedupe) return false;
    this.events.set(candidate.event_id, now + VOICE_LIMITS.dedupeMs); this.activities.set(candidate.activity_id, now + VOICE_LIMITS.dedupeMs); return true;
  }
  consume(frame: unknown, identity: VoiceIdentity): boolean {
    if (this.disposed || !this.same(identity)) return false;
    const arrived = this.elapsed();
    this.tick(); const candidate = candidateFromFrame(frame);
    if (!Number.isFinite(arrived) || !candidate || !this.remember(candidate, arrived)) return false;
    // Server timestamps are metadata only: clock skew must never discard a live event.
    if (!this.permitted(this.now()) || this.preferences.disabled.has(candidate.subscription_id) || arrived < this.notBefore || this.queue.length + (this.active ? 1 : 0) >= VOICE_LIMITS.queue) return false;
    this.queue.push({ candidate, expires: arrived + VOICE_LIMITS.ttlMs }); this.pump(); this.publish(); return true;
  }
  private current(job: Job): boolean { return !this.disposed && this.active === job && job.generation === this.generation && !job.abort.signal.aborted; }
  private finish(job: Job): void {
    if (!this.current(job)) return;
    this.active = undefined; this.clock.clearTimeout(job.timer); job.abort.abort();
    if (job.phase === "starting") { try { this.options.speech.cancel(); } catch { /* An expired browser queue must not be retried. */ } }
    this.pump(); this.publish();
  }
  private fail(job: Job): void {
    if (!this.current(job)) return;
    this.failed = true; this.armed = false; this.activatedInSession = false; this.dropAll(); this.publish();
  }
  private pump(): void {
    if (this.active || !this.permitted(this.now()) || !this.session) return;
    let next: Pending | undefined;
    while ((next = this.queue.shift())) if (next.expires > this.elapsed() && !this.preferences.disabled.has(next.candidate.subscription_id)) break;
    if (!next || next.expires <= this.elapsed()) return;
    const job: Job = { ...next, abort: new AbortController(), generation: this.generation, phase: "resolving", timer: undefined };
    this.active = job;
    job.timer = this.clock.setTimeout(() => this.finish(job), Math.min(VOICE_LIMITS.metadataMs, job.expires - this.elapsed()));
    const context = Object.freeze({ ...this.session, signal: job.abort.signal });
    Promise.resolve().then(() => this.current(job) ? this.options.resolveMetadata(job.candidate, context) : null).then(value => {
      if (!this.current(job)) return;
      const metadata = verifiedMetadata(value, job.candidate);
      if (!metadata || !this.permitted(this.now()) || job.expires <= this.elapsed() || this.preferences.disabled.has(job.candidate.subscription_id)) { this.finish(job); return; }
      this.clock.clearTimeout(job.timer); job.phase = "starting";
      job.timer = this.clock.setTimeout(() => this.fail(job), VOICE_LIMITS.speechMs);
      this.publish();
      try {
        this.options.speech.speak(`${metadata.project_name}，${metadata.rating}级。`, {
          start: () => {
            if (!this.current(job)) return;
            if (!this.permitted(this.now()) || job.expires <= this.elapsed()) { this.dropAll(); this.publish(); return; }
            job.phase = "speaking"; this.publish();
          },
          end: () => this.finish(job), error: () => this.fail(job),
        });
      } catch { this.fail(job); }
    }).catch(() => this.finish(job));
    this.publish();
  }
  /** Also safe to call on visibility/resume; timers never refill a dropped queue. */
  tick(): void {
    if (this.disposed) return;
    const now = this.now();
    if (!this.permitted(now)) {
      if (this.active || this.queue.length) this.dropAll();
    } else {
      const elapsed = this.elapsed();
      this.queue = this.queue.filter(item => item.expires > elapsed);
      if (this.active && this.active.phase !== "speaking" && this.active.expires <= elapsed) { const job = this.active; this.finish(job); }
      this.pump();
    }
    this.clock.clearTimeout(this.timer); this.timer = undefined;
    if (this.session && this.preferences.enabled && this.armed && this.connected && !this.failed && this.availability() === "available" && Number.isFinite(now)) {
      const boundary = nextVoiceBoundaryMs(now, this.preferences.quiet);
      this.timer = this.clock.setTimeout(() => this.tick(), isVoiceQuietHours(now, this.preferences.quiet) ? boundary : Math.min(1000, boundary));
    }
    this.publish();
  }
  /** Personal browser preference: change or disable the quiet window (Asia/Shanghai hours). */
  setQuietHours(quiet: VoiceQuietHours): boolean {
    if (this.disposed || !this.session || typeof quiet.enabled !== "boolean" || !validHour(quiet.start) || !validHour(quiet.end)) return false;
    this.preferences.quiet = { enabled: quiet.enabled, start: quiet.start, end: quiet.end }; this.persist(); this.tick(); return true;
  }
  quietHours(): VoiceQuietHours { return { ...this.preferences.quiet }; }
  destroy(): void {
    if (this.disposed) return;
    this.dropAll(); this.session = null; this.armed = false; this.activatedInSession = false; this.connected = false; this.disposed = true;
    this.stopObserving?.(); this.stopObserving = undefined; this.publish(); this.listeners.clear(); this.events.clear(); this.activities.clear();
  }
}
