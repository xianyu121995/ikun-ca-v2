import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { TrackingVoiceController } from "../controller.ts";
import { candidateFromFrame, isVoiceQuietHours, nextVoiceBoundaryMs, VOICE_LIMITS } from "../validation.ts";
import { voicePreferenceKey } from "../preferences.ts";
import { createWebSpeechPort, bindVoiceBrowserLifecycle } from "../browser.ts";
import { VoiceControls } from "../controls.tsx";
import { FakeClock, MockSpeech, MemoryStorage, frame, metadata, session, initialTime, uuid, flush, gesture } from "./helpers.mjs";

function fixture(options = {}) {
  const clock = options.clock ?? new FakeClock(), speech = options.speech ?? new MockSpeech(), storage = options.storage ?? new MemoryStorage();
  const resolved = [];
  const resolveMetadata = options.resolveMetadata ?? (async (candidate, context) => { resolved.push({ candidate, context }); return metadata(candidate); });
  const voice = new TrackingVoiceController({ speech, storage, clock, resolveMetadata });
  const identity = options.session ?? session;
  voice.setSession(identity); voice.setStreamConnected(true, identity);
  return { clock, speech, storage, voice, resolved, identity, enable: () => voice.enableFromGesture(gesture), send: (n = 1, patch = {}, outer = {}) => voice.consume(frame(n, clock.now(), patch, outer), identity) };
}

test("defaults off, rejects invalid session and requires a real gesture on every page", async () => {
  const f = fixture(); assert.equal(f.voice.getSnapshot().status, "off"); assert.equal(f.send(), false); assert.equal(f.resolved.length, 0);
  assert.equal(f.voice.enableFromGesture({ isTrusted: false }), false); assert.equal(f.send(2), false);
  f.voice.setSession({ ...session, user_id: "" }); assert.equal(f.voice.getSnapshot().status, "signed-out");
  assert.equal(f.enable(), false); f.voice.destroy();
});
for (const role of ["user", "superadmin"]) for (const kind of ["original", "quote"]) {
  test(`${role} may enable personal voice for ${kind}, independently of business write permission`, async () => {
    const f = fixture({ session: { ...session, role } }); assert.equal(f.enable(), true); assert.equal(f.send(1, { tweet_kind: kind, text: "NEVER SPEAK THIS", x_handle: "not_a_note", name: "not_a_note", raw: { secret: "none" } }), true);
    await flush(); assert.deepEqual(f.speech.calls, ["真实监控备注，A级。"]);
    assert.deepEqual(Object.keys(f.resolved[0].candidate).sort(), ["event_id", "activity_id", "subscription_id", "project_id", "tweet_kind", "received_at"].sort());
    assert.equal(f.resolved[0].context.role, role); assert.equal(f.voice.getSnapshot().status, "speaking"); f.speech.end(); assert.equal(f.voice.getSnapshot().status, "ready"); f.voice.destroy();
  });
}
for (const rating of ["S", "A", "B"]) test(`only true notes plus current ${rating} rating are spoken`, async () => {
  const f = fixture({ resolveMetadata: async c => metadata(c, { rating, notes: "  真实\n备注  " }) }); f.enable(); f.send(); await flush(); assert.deepEqual(f.speech.calls, [`真实 备注，${rating}级。`]); f.voice.destroy();
});
test("C/D/null/missing and invalid metadata never fall back to event name, handle or rating", async () => {
  const patches = [{ rating: "C" }, { rating: "D" }, { rating: null }, { rating: undefined }, { rating: 90 }, { notes: "" }, { notes: " \n\t" }, { notes: "\u200b" }, { notes: "\u202e备注" }, { notes: 2 }, { notes: "a".repeat(4001) }, { subscription_revision: 0 }, { subscription_revision: "1" }, { project_revision: -1 }, { project_revision: NaN }, { project_revision: Infinity }, { subscription_id: "sub_" + uuid(2) }, { project_id: "prj_" + uuid(2) }];
  for (const patch of patches) { const f = fixture({ resolveMetadata: async c => metadata(c, patch) }); f.enable(); f.send(1, { notes: "不可回退", rating: "S", name: "不可回退" }); await flush(); assert.equal(f.speech.calls.length, 0, JSON.stringify(patch)); f.voice.destroy(); }
});
test("failed/null HTTP wrappers are not accepted as verified metadata; resolver throw is isolated", async () => {
  for (const value of [null, { ok: true, data: metadata(frame().data) }, { error: { code: "NOT_FOUND" } }]) { const f = fixture({ resolveMetadata: async () => value }); f.enable(); f.send(); await flush(); assert.equal(f.speech.calls.length, 0); f.voice.destroy(); }
  const f = fixture({ resolveMetadata: async () => { throw Error("private response must not be logged"); } }); f.enable(); f.send(); await flush(); assert.equal(f.voice.getSnapshot().status, "ready"); assert.equal(f.speech.calls.length, 0); f.voice.destroy();
});
test("strict event parser accepts UUIDv5 activities and rejects other types, origins and unreliable fields", () => {
  assert.ok(candidateFromFrame(frame())); assert.ok(candidateFromFrame(frame(2, initialTime, { activity_id: "act_" + uuid(2, 4) })));
  const patches = [{ tweet_kind: "reply" }, { tweet_kind: "retweet" }, { tweet_kind: "unknown" }, { tweet_kind: null }, { source: "rest" }, { source: "rest_recovery" }, { source: "unknown" }, { source: undefined }, { replay: true }, { replay: undefined }, { is_live_new: false }, { is_live_new: 1 }, { received_at: "2026-02-31T10:00:00Z" }, { received_at: "invalid" }, { received_at: "2026-10-16T12:00:00+08:00" }, { activity_id: "bad" }, { subscription_id: "sub_" + uuid(1, 5) }, { project_id: "bad" }];
  for (const patch of patches) assert.equal(candidateFromFrame(frame(1, initialTime, patch)), null, JSON.stringify(patch));
  for (const delivery of ["history", "replay", "rest", undefined]) assert.equal(candidateFromFrame(frame(1, initialTime, {}, { delivery })), null);
  for (const type of ["tracking.feed.activity.updated.v1", "tracking.activity.created", "hunter.discovery.created", "message"]) assert.equal(candidateFromFrame(frame(1, initialTime, {}, { type })), null);
  assert.equal(candidateFromFrame(frame(1, initialTime, {}, { event_id: "missing" })), null);
});
test("old/future timestamps and invalid delivery never reach metadata", async () => {
  const f = fixture(); f.enable();
  assert.equal(f.voice.consume(frame(1, f.clock.now() - 30000), f.identity), false);
  assert.equal(f.voice.consume(frame(2, f.clock.now() + 1), f.identity), false);
  for (const delivery of ["history", "replay", "rest"]) assert.equal(f.send(3, {}, { delivery }), false);
  assert.equal(f.send(4, { replay: true }), false); await flush(); assert.equal(f.resolved.length, 0); f.voice.destroy();
});
test("both stable event and activity IDs deduplicate before and after completion", async () => {
  const f = fixture(); f.enable(); assert.equal(f.send(), true); await flush(); f.speech.end();
  assert.equal(f.send(1, { activity_id: "act_" + uuid(2, 5) }), false);
  assert.equal(f.send(2, { activity_id: "act_" + uuid(1, 5) }), false);
  assert.equal(f.send(), false); await flush(); assert.equal(f.speech.calls.length, 1); f.voice.destroy();
});
test("disable, per-subscription off, logout, revoke, user switch, disconnect, page close and destroy invalidate late metadata", async () => {
  for (const action of ["off", "subscription", "logout", "epoch", "user", "disconnect", "suspend", "destroy", "preferences"]) {
    let answer, signal;
    const f = fixture({ resolveMetadata: (c, context) => { signal = context.signal; return new Promise(resolve => { answer = () => resolve(metadata(c)); }); } });
    f.enable(); f.send(); await flush(); assert.equal(signal.aborted, false);
    if (action === "off") f.voice.disable();
    if (action === "subscription") f.voice.setSubscriptionEnabled("sub_" + uuid(1), false);
    if (action === "logout") f.voice.setSession(null);
    if (action === "epoch") f.voice.setSession({ ...session, epoch: "session-2" });
    if (action === "user") f.voice.setSession({ ...session, user_id: "usr_" + uuid(2) });
    if (action === "disconnect") f.voice.setStreamConnected(false, session);
    if (action === "suspend") f.voice.suspend();
    if (action === "destroy") f.voice.destroy();
    if (action === "preferences") f.voice.reloadPreferences();
    assert.equal(signal.aborted, true, action); answer(); await flush(); assert.equal(f.speech.calls.length, 0, action); assert.equal(f.voice.getSnapshot().queued, 0, action); f.voice.destroy();
  }
});
test("all stop actions cancel active speech immediately, including a speaking subscription switched off", async () => {
  for (const action of [f => f.voice.disable(), f => f.voice.setSession(null), f => f.voice.setSession({ ...session, epoch: "changed" }), f => f.voice.setStreamConnected(false, session), f => f.voice.setSubscriptionEnabled("sub_" + uuid(1), false), f => f.voice.suspend()]) {
    const f = fixture(); f.enable(); f.send(); await flush(); const before = f.speech.cancellations; action(f); assert.ok(f.speech.cancellations > before); assert.equal(f.speech.hooks, null); assert.equal(f.voice.getSnapshot().queued, 0); f.voice.destroy();
  }
});
test("old session callbacks cannot reconnect or inject work into a new session", async () => {
  const f = fixture(); f.enable(); f.voice.setSession({ ...session, epoch: "new" });
  f.voice.setStreamConnected(true, session); assert.equal(f.voice.getSnapshot().connected, false); assert.equal(f.send(), false); assert.equal(f.speech.calls.length, 0); f.voice.destroy();
});
test("disconnect requires a fresh gesture; reconnect does not replay earlier received events", async () => {
  const f = fixture(); f.enable(); f.voice.setStreamConnected(false, session); f.clock.advance(1000); f.voice.setStreamConnected(true, session);
  assert.equal(f.voice.getSnapshot().armed, false); f.enable(); assert.equal(f.voice.consume(frame(1, initialTime), session), false);
  assert.equal(f.send(2), true); await flush(); assert.equal(f.speech.calls.length, 1); f.voice.destroy();
});
test("global and per-subscription disabled events are dropped and never buffered for later", async () => {
  const f = fixture(); assert.equal(f.send(), false); f.enable(); assert.equal(f.send(), false);
  f.voice.setSubscriptionEnabled("sub_" + uuid(1), false); assert.equal(f.send(2), false);
  f.voice.setSubscriptionEnabled("sub_" + uuid(1), true); assert.equal(f.send(2), false); f.send(3); await flush(); assert.equal(f.speech.calls.length, 1); f.voice.destroy();
});
test("bounded queue admits at most 20, drops overflow and expires waiting items after 30 seconds", async () => {
  const f = fixture(); f.enable(); for (let n = 1; n <= 20; n++) assert.equal(f.send(n), true); assert.equal(f.send(21), false);
  await flush(); assert.equal(f.voice.getSnapshot().queued, 20); assert.equal(f.speech.calls.length, 1);
  f.clock.time += 30_000; f.speech.end(); await flush(); assert.equal(f.voice.getSnapshot().queued, 0); assert.equal(f.speech.calls.length, 1); f.voice.destroy();
});
test("dedupe capacity is bounded without evicting live IDs; overflow cannot replay an earlier event", async () => {
  const f = fixture(); for (let n = 1; n <= 2000; n++) f.send(n); // all off: remember and discard, no metadata
  assert.equal(f.voice.events.size, VOICE_LIMITS.dedupe); assert.equal(f.voice.activities.size, VOICE_LIMITS.dedupe);
  f.enable(); assert.equal(f.send(1), false); await flush(); assert.equal(f.speech.calls.length, 0); f.voice.destroy();
});
test("metadata timeout aborts at four seconds and ignores even a successful late answer", async () => {
  let answer, signal;
  const f = fixture({ resolveMetadata: (c, context) => { signal = context.signal; return new Promise(resolve => { answer = () => resolve(metadata(c)); }); } });
  f.enable(); f.send(); await flush(); f.clock.advance(4000); assert.equal(signal.aborted, true); answer(); await flush(); assert.equal(f.speech.calls.length, 0); assert.equal(f.voice.getSnapshot().queued, 0); f.voice.destroy();
});
test("speech error and missing browser callbacks fail closed without retrying or blocking the feed", async () => {
  for (const error of [true, false]) { const f = fixture(); f.enable(); f.send(); await flush(); if (error) f.speech.error(); else f.clock.advance(30000); assert.equal(f.voice.getSnapshot().status, "failed"); assert.equal(f.voice.getSnapshot().armed, false); assert.equal(f.send(2), false); assert.equal(f.speech.calls.length, 1); f.voice.destroy(); }
});
test("native queued speech that never started is cancelled when its event TTL expires", async () => {
  const f = fixture(); f.speech.startImmediately = false; f.enable(); f.send(); await flush();
  assert.equal(f.voice.getSnapshot().status, "starting"); const before = f.speech.cancellations;
  f.clock.time += 30000; f.voice.tick(); assert.ok(f.speech.cancellations > before); assert.equal(f.speech.hooks, null); f.voice.destroy();
});
test("quiet time is Shanghai 22 inclusive to 08 exclusive regardless of host timezone", () => {
  for (const [at, quiet] of [["2026-10-16T13:59:59.999Z", false], ["2026-10-16T14:00:00.000Z", true], ["2026-10-16T23:59:59.999Z", true], ["2026-10-17T00:00:00.000Z", false]]) assert.equal(isVoiceQuietHours(Date.parse(at)), quiet, at);
});
test("crossing exactly 22 stops speaking and drops queued work; quiet events do not accumulate until 08", async () => {
  const clock = new FakeClock(); clock.time = Date.parse("2026-10-16T13:59:59.000Z"); const f = fixture({ clock }); f.enable(); f.send(1); f.send(2); await flush();
  clock.advance(1000); assert.equal(f.voice.getSnapshot().status, "quiet-hours"); assert.equal(f.voice.getSnapshot().queued, 0); assert.equal(f.speech.hooks, null);
  const quietFrame = frame(3, clock.now()); f.voice.consume(quietFrame, session); clock.advance(10 * 3600_000); await flush(); assert.equal(f.speech.calls.length, 1); assert.equal(f.voice.consume(quietFrame, session), false); assert.equal(f.send(4), true); await flush(); assert.equal(f.speech.calls.length, 2); f.voice.destroy();
});
test("metadata completed at 22 or a backwards wall clock cannot reopen a quiet queue", async () => {
  const clock = new FakeClock(); clock.time = Date.parse("2026-10-16T13:59:59.000Z"); let answer;
  const f = fixture({ clock, resolveMetadata: c => new Promise(resolve => { answer = () => resolve(metadata(c)); }) }); f.enable(); f.send(); await flush(); clock.advance(1000); answer(); await flush(); assert.equal(f.speech.calls.length, 0);
  clock.time -= 2000; f.voice.tick(); assert.equal(f.voice.getSnapshot().status, "quiet-hours"); f.voice.destroy();
});
test("stored preference is user-isolated, contains no notes/session/events, and never unlocks another page", async () => {
  const storage = new MemoryStorage(); const f = fixture({ storage }); f.enable(); f.voice.setSubscriptionEnabled("sub_" + uuid(2), false); f.send(); await flush();
  const raw = storage.getItem(voicePreferenceKey(session.user_id)); assert.deepEqual(Object.keys(JSON.parse(raw)).sort(), ["version", "enabled", "disabled_subscription_ids", "quiet_hours"].sort()); assert.ok(!raw.includes("真实")); assert.ok(!raw.includes(session.epoch)); f.voice.destroy();
  const otherPage = fixture({ storage }); assert.equal(otherPage.voice.getSnapshot().enabled, true); assert.equal(otherPage.voice.getSnapshot().armed, false); assert.equal(otherPage.send(), false); otherPage.voice.destroy();
  const otherUser = fixture({ storage, session: { ...session, user_id: "usr_" + uuid(2) } }); assert.equal(otherUser.voice.getSnapshot().enabled, false); assert.deepEqual(otherUser.voice.getSnapshot().disabled_subscription_ids, []); otherUser.voice.destroy();
});
test("corrupt, oversized and blocked storage honestly fall back to page-only defaults", () => {
  for (const value of ["not-json", "a".repeat(70000), JSON.stringify({ version: 1, enabled: true, disabled_subscription_ids: ["bad"] })]) { const storage = new MemoryStorage(); storage.setItem(voicePreferenceKey(session.user_id), value); const f = fixture({ storage }); assert.equal(f.voice.getSnapshot().enabled, false); f.voice.destroy(); }
  const f = fixture({ storage: { getItem() { throw Error("denied"); }, setItem() { throw Error("denied"); } } }); assert.equal(f.voice.getSnapshot().storage_available, false); assert.equal(f.enable(), true); assert.equal(f.voice.getSnapshot().storage_available, false); f.voice.destroy();
});
test("unsupported and missing local voices are disabled and cannot enqueue or enable", () => {
  for (const state of ["unsupported", "no-local-voice"]) { const speech = new MockSpeech(); speech.state = state; const f = fixture({ speech }); assert.equal(f.enable(), false); assert.equal(f.send(), false); assert.equal(f.voice.getSnapshot().status, state); const html = renderToStaticMarkup(createElement(VoiceControls, { controller: f.voice })); assert.match(html, /disabled/); assert.match(html, /不可用/); f.voice.destroy(); }
  assert.equal(createWebSpeechPort().availability(), "unsupported");
});
test("local voice loss cancels playback and requires a fresh gesture when voices return", async () => {
  const f = fixture(); f.enable(); f.send(); await flush(); f.speech.state = "no-local-voice"; f.speech.observer(); assert.equal(f.speech.hooks, null); assert.equal(f.voice.getSnapshot().status, "no-local-voice"); f.speech.state = "available"; f.speech.observer(); assert.equal(f.voice.getSnapshot().armed, false); f.voice.destroy();
});
test("browser adapter selects only a local voice, reports start separately, and never speaks on construction/unlock", () => {
  let spoken, cancelled = 0; const listeners = new Map();
  const local = { localService: true, lang: "zh-CN", name: "local" }, remote = { localService: false, default: true, lang: "zh-CN", name: "remote" };
  const target = { SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } }, navigator: { userActivation: { isActive: true } }, speechSynthesis: { getVoices: () => [remote, local], speak: value => { spoken = value; }, cancel: () => cancelled++, addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name) } };
  const port = createWebSpeechPort(target); assert.equal(port.availability(), "available"); assert.equal(port.isUserGesture(gesture), true); assert.equal(spoken, undefined);
  assert.equal(port.isUserGesture({ ...gesture, isTrusted: false }), false); target.navigator.userActivation.isActive = false; assert.equal(port.isUserGesture(gesture), false);
  let started = false; port.speak("真实备注，S级。", { start: () => { started = true; }, end() {}, error() {} }); assert.equal(spoken.voice, local); assert.equal(started, false); spoken.onstart(); assert.equal(started, true);
  port.cancel(); assert.equal(cancelled, 1); assert.equal(spoken.onstart, null);
  target.speechSynthesis.getVoices = () => [remote]; assert.equal(port.availability(), "no-local-voice");
  const stop = port.observe(() => {}); assert.equal(listeners.size, 1); stop(); assert.equal(listeners.size, 0);
});
test("browser lifecycle cancels pagehide/freeze, reloads personal storage, and disposes all listeners", () => {
  const target = new EventTarget(); target.document = new EventTarget(); const f = fixture();
  const cleanup = bindVoiceBrowserLifecycle(f.voice, target); f.enable(); target.dispatchEvent(new Event("pagehide")); assert.equal(f.voice.getSnapshot().armed, false);
  f.voice.setStreamConnected(true, session); f.enable(); target.document.dispatchEvent(new Event("freeze")); assert.equal(f.voice.getSnapshot().armed, false);
  f.voice.setStreamConnected(true, session); f.enable(); const event = new Event("storage"); event.key = voicePreferenceKey(session.user_id); target.dispatchEvent(event); assert.equal(f.voice.getSnapshot().armed, false); cleanup(); assert.equal(f.voice.getSnapshot().status, "signed-out"); assert.equal(f.clock.timers.size, 0);
});

test("owner-configurable quiet hours: custom window, same-day window and disabled", () => {
  const at = iso => Date.parse(iso);
  const night = { enabled: true, start: 0, end: 7 };
  assert.equal(isVoiceQuietHours(at("2026-10-16T16:30:00.000Z"), night), true);   // 00:30 Shanghai
  assert.equal(isVoiceQuietHours(at("2026-10-16T23:30:00.000Z"), night), false);  // 07:30 Shanghai
  const noon = { enabled: true, start: 12, end: 14 };
  assert.equal(isVoiceQuietHours(at("2026-10-17T04:30:00.000Z"), noon), true);    // 12:30 Shanghai
  assert.equal(isVoiceQuietHours(at("2026-10-17T07:00:00.000Z"), noon), false);   // 15:00 Shanghai
  assert.equal(isVoiceQuietHours(at("2026-10-16T16:30:00.000Z"), { enabled: false, start: 22, end: 8 }), false);
  assert.equal(nextVoiceBoundaryMs(at("2026-10-17T04:30:00.000Z"), noon), 90 * 60_000);
});
