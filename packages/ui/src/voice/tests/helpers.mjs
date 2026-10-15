export const uuid = (n = 1, version = 4) => `00000000-0000-${version}000-8000-${n.toString(16).padStart(12, "0")}`;
export const session = { user_id: "usr_" + uuid(1), epoch: "session-1", role: "user" };
export const initialTime = Date.parse("2026-10-16T04:00:00.000Z");
export const frame = (n = 1, now = initialTime, patch = {}, outer = {}) => ({
  type: "tracking.feed.activity.created.v1", delivery: "live", event_id: "evt_" + uuid(n),
  data: { activity_id: "act_" + uuid(n, 5), subscription_id: "sub_" + uuid(1), project_id: "prj_" + uuid(1), tweet_kind: "original", source: "wss", is_live_new: true, replay: false, received_at: new Date(now).toISOString(), ...patch }, ...outer,
});
export const metadata = (candidate, patch = {}) => ({ subscription_id: candidate.subscription_id, project_id: candidate.project_id, notes: "真实监控备注", subscription_revision: 3, rating: "A", project_revision: 7, ...patch });
export const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
export class FakeClock {
  time = initialTime; id = 0; timers = new Map();
  now = () => this.time;
  setTimeout = (fn, ms) => { const id = ++this.id; this.timers.set(id, { fn, at: this.time + ms }); return id; };
  clearTimeout = id => this.timers.delete(id);
  advance(ms) { const until = this.time + ms; let guard = 0; for (;;) { const next = [...this.timers.entries()].filter(([, t]) => t.at <= until).sort((a, b) => a[1].at - b[1].at)[0]; if (!next) break; if (++guard > 20000) throw Error("timer loop"); this.time = next[1].at; this.timers.delete(next[0]); next[1].fn(); } this.time = until; }
}
export class MemoryStorage {
  values = new Map(); getItem = key => this.values.get(key) ?? null; setItem = (key, value) => { this.values.set(key, value); };
}
export class MockSpeech {
  state = "available"; calls = []; cancellations = 0; hooks = null; observer = null; startImmediately = true;
  availability = () => this.state;
  isUserGesture = event => event?.isTrusted === true;
  speak = (text, hooks) => { this.calls.push(text); this.hooks = hooks; if (this.startImmediately) hooks.start(); };
  cancel = () => { this.cancellations++; this.hooks = null; };
  observe = listener => { this.observer = listener; return () => { this.observer = null; }; };
  end() { const hooks = this.hooks; this.hooks = null; hooks?.end(); }
  error() { const hooks = this.hooks; this.hooks = null; hooks?.error(); }
}
export const gesture = { isTrusted: true, type: "click" };
