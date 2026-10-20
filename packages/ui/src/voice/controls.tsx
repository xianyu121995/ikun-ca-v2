"use client";
import { useState, useSyncExternalStore } from "react";
import { Button } from "../primitives.js";
import type { TrackingVoiceController } from "./controller.js";
import type { VoiceStatus } from "./types.js";
import { isSubscriptionId } from "./validation.js";

const labels: Record<VoiceStatus, string> = {
  "signed-out": "登录后可启用语音", unsupported: "此浏览器不支持 Web Speech，语音不可用", "no-local-voice": "未发现本机音色，语音不可用",
  off: "语音已关闭", locked: "本页待启用，请点击启用按钮", disconnected: "实时连接已断开，已停止并清空播报",
  "quiet-hours": "当前处于静音时段，期间事件不补播", ready: "已启用，等待实时新推文",
  resolving: "正在核对项目名称与评分", starting: "正在请求浏览器播放，尚未确认开始", speaking: "浏览器报告正在播报",
  failed: "未取得播放许可或语音播放失败，请重新点击启用",
};
const hours = Array.from({ length: 24 }, (_, h) => h);
const pad = (h: number) => String(h).padStart(2, "0");
export interface VoiceControlsProps { controller: TrackingVoiceController; subscriptions?: readonly { subscription_id: string; label: string }[] }
/** Personal browser preferences are available to both user and superadmin; these are not business writes. */
export function VoiceControls({ controller, subscriptions = [] }: VoiceControlsProps) {
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const [preferenceError, setPreferenceError] = useState(false);
  const unavailable = state.status === "signed-out" || state.available !== "available";
  return <section className="ik-theme ik-stack" aria-label="推文语音设置">
    <div className="ik-actions"><strong>实时推文语音</strong>
      <Button size="sm" variant="primary" disabled={unavailable || state.armed} aria-pressed={state.armed && state.enabled} onClick={event => controller.enableFromGesture(event.nativeEvent)}>启用本页语音</Button>
      <Button size="sm" disabled={!state.enabled} onClick={() => controller.disable()}>关闭语音</Button>
    </div>
    <div className="ik-actions" aria-label="静音时段">
      <label className="ik-actions"><input type="checkbox" disabled={unavailable} checked={state.quiet_hours.enabled} onChange={event => controller.setQuietHours({ ...state.quiet_hours, enabled: event.target.checked })} /><span>静音时段（北京时间）</span></label>
      <select aria-label="静音开始" disabled={unavailable || !state.quiet_hours.enabled} value={state.quiet_hours.start} onChange={event => controller.setQuietHours({ ...state.quiet_hours, start: Number(event.target.value) })}>{hours.map(h => <option key={h} value={h}>{pad(h)}:00</option>)}</select>
      <span>至</span>
      <select aria-label="静音结束" disabled={unavailable || !state.quiet_hours.enabled} value={state.quiet_hours.end} onChange={event => controller.setQuietHours({ ...state.quiet_hours, end: Number(event.target.value) })}>{hours.map(h => <option key={h} value={h}>{pad(h)}:00</option>)}</select>
    </div>
    <p role="status" className="ik-hint">{labels[state.status]}{state.status === "quiet-hours" ? `（${pad(state.quiet_hours.start)}:00–${pad(state.quiet_hours.end)}:00）` : ""}{state.queued > 0 ? ` · 等待/播放 ${state.queued} 项` : ""}</p>
    <p className="ik-hint">播报项目名称和 S/A/B 等级，无需填写备注。偏好仅保存在本浏览器；每页需主动启用，静音时不积压。</p>
    {!state.storage_available && <p className="ik-hint">浏览器偏好存储不可用，当前设置仅本页有效。</p>}
    {preferenceError && <p role="alert" className="ik-field-error">逐账号偏好已达上限，请先恢复部分逐账号开关。</p>}
    {subscriptions.filter(item => isSubscriptionId(item.subscription_id)).slice(0, 1000).map(item => <label key={item.subscription_id} className="ik-actions">
      <input type="checkbox" disabled={unavailable} checked={!state.disabled_subscription_ids.includes(item.subscription_id)} onChange={event => setPreferenceError(!controller.setSubscriptionEnabled(item.subscription_id, event.target.checked))} />
      <span>{item.label}：允许语音</span>
    </label>)}
  </section>;
}
