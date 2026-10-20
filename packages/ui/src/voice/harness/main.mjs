import React, { useState, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import { TrackingVoiceController } from "../controller.ts";
import { VoiceControls } from "../controls.tsx";
import { Button, Panel, Select } from "../../primitives.tsx";
import { FakeClock, MockSpeech, MemoryStorage, frame, metadata, session, uuid } from "../tests/helpers.mjs";
import "../../styles.css";

const e = React.createElement;
const clock = new FakeClock(), speech = new MockSpeech(), storage = new MemoryStorage();
let identity = { ...session }, serial = 0, requests = 0, aborted = 0, holdNext = false, lateAnswer;
const results = new Map();
const voice = new TrackingVoiceController({ clock, speech, storage, resolveMetadata: (candidate, context) => {
  requests++; context.signal.addEventListener("abort", () => aborted++, { once: true });
  const answer = metadata(candidate, results.get(candidate.event_id) ?? {});
  if (holdNext) { holdNext = false; return new Promise(resolve => { lateAnswer = () => resolve(answer); }); }
  return Promise.resolve(answer);
} });
voice.setSession(identity); voice.setStreamConnected(true, identity);
function App() {
  const state = useSyncExternalStore(voice.subscribe, voice.getSnapshot, voice.getSnapshot);
  const [, redraw] = useState(0);
  const act = fn => () => { fn(); redraw(v => v + 1); };
  function send(kind = "original", patch = {}, outer = {}, meta = {}) {
    const input = frame(++serial, clock.now(), { tweet_kind: kind, ...patch }, outer);
    results.set(input.event_id, meta); voice.consume(input, identity);
  }
  function role(value) { identity = { ...session, role: value, epoch: `page-${++serial}` }; voice.setSession(identity); voice.setStreamConnected(true, identity); }
  const button = (label, fn) => e(Button, { key: label, size: "sm", onClick: act(fn) }, label);
  return e("main", { className: "ik-theme ik-stack", style: { padding: 24, maxWidth: 1100, margin: "0 auto" } },
    e("h1", null, "语音组件 · 无声验收"),
    e("p", { className: "ik-hint" }, "独立合成夹具，仅调用 mock 输出；没有 EventSource、业务请求或真实扬声。虚拟时间与系统时间无关。"),
    e(Select, { label: "演示角色", value: identity.role, onChange: ev => { role(ev.target.value); redraw(v => v + 1); } }, e("option", { value: "user" }, "user"), e("option", { value: "superadmin" }, "superadmin")),
    e(Panel, { title: "组件控件" }, e(VoiceControls, { controller: voice, subscriptions: [{ subscription_id: "sub_" + uuid(1), label: "合成项目账号" }] })),
    e(Panel, { title: "无声事件与生命周期" }, e("div", { className: "ik-actions", style: { flexWrap: "wrap" } },
      button("模拟原创", () => send()), button("模拟引用", () => send("quote")),
      button("模拟重复", () => voice.consume(frame(serial, clock.now()), identity)),
      button("模拟重放", () => send("original", { replay: true })), button("模拟 REST", () => send("original", { source: "rest" })),
      button("模拟空项目名称", () => send("original", {}, {}, { project_name: "" })), button("模拟 C 级", () => send("original", {}, {}, { rating: "C" })),
      button("结束当前播放", () => speech.end()), button("模拟播放失败", () => speech.error()),
      button("挂起下一次项目查询", () => { holdNext = true; }), button("返回迟到结果", () => { lateAnswer?.(); lateAnswer = undefined; }),
      button("退出登录", () => voice.setSession(null)), button("恢复登录", () => role(identity.role)),
      button("断开实时流", () => voice.setStreamConnected(false, identity)), button("重新连接", () => voice.setStreamConnected(true, identity)),
      button("切换到 22:00", () => { clock.time = Date.parse("2026-10-16T14:00:00Z"); voice.tick(); }),
      button("切换到次日 08:00", () => { clock.time = Date.parse("2026-10-17T00:00:00Z"); voice.tick(); }),
      button("移除本机音色", () => { speech.state = "no-local-voice"; speech.observer?.(); }),
      button("恢复本机音色", () => { speech.state = "available"; speech.observer?.(); }),
      button("重置夹具", () => location.reload())
    )),
    e(Panel, { title: "输出证据（仅 mock）" }, e("pre", { "data-testid": "voice-proof", style: { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } }, JSON.stringify({ audio: "mock-only", identity: identity.role, status: state.status, armed: state.armed, enabled: state.enabled, queued: state.queued, spoken: speech.calls, cancellations: speech.cancellations, requests, aborted, time: new Date(clock.now()).toISOString() }, null, 2)))
  );
}
window.addEventListener("pagehide", () => voice.destroy(), { once: true });
createRoot(document.getElementById("root")).render(e(App));
