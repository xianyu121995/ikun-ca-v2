"use client";
import { useState, type ReactNode } from "react";
import { Button, Select } from "@ikun/ui";
import { TrackingView } from "./tracking-view";
import { demoActivities, demoIncomingActivities, demoProject, demoSubscriptions, fixtureCommandId, fixtureTime, subscriptionIds } from "./demo-fixtures";
import type { ActionInput, AddInput, CommandDTO, PublicError, SubscriptionDTO } from "./types";
import s from "./tracking.module.css";

type Scenario = "success" | "denied" | "timeout" | "conflict" | "pending" | "unknown";
const wait = () => new Promise<void>(resolve => setTimeout(resolve, 700));
const fixtureError = (code: string, message: string): PublicError => ({ code, message, retryable: false, request_id: "demo-request-001" });
/** Explicit demo-only callbacks. No transport, storage, identity or engine. */
export function TrackingDemo({ toolbarSlot }: { toolbarSlot?: ReactNode }) {
  const [rows, setRows] = useState(demoSubscriptions), [scenario, setScenario] = useState<Scenario>("success");
  const [role, setRole] = useState<"superadmin" | "user">("superadmin"), [screen, setScreen] = useState("data");
  const [refreshing, setRefreshing] = useState(false), [refreshError, setRefreshError] = useState<PublicError | null>(null);
  const [calls, setCalls] = useState<string[]>([]);
  const [activities, setActivities] = useState(demoActivities), [incoming, setIncoming] = useState(0);
  function log(value: string) { setCalls(old => [...old, value]); }
  async function result(project_id: string, subscription_id: string | null, revision: number): Promise<CommandDTO> {
    await wait();
    if (scenario === "denied") throw fixtureError("FORBIDDEN", "演示回调拒绝了管理权限。");
    if (scenario === "timeout") throw fixtureError("UPSTREAM_TIMEOUT", "演示写入超时，结果待核实；先查询原回执。");
    if (scenario === "conflict") throw fixtureError("VERSION_CONFLICT", "演示 revision 冲突，请刷新核对。");
    return { command_id: fixtureCommandId, state: scenario === "pending" ? "accepted" : scenario === "unknown" ? "unknown" : "succeeded", project_id, subscription_id, revision: revision + 1, updated_at: fixtureTime, error_code: null, request_id: "demo-request-001" };
  }
  async function onAction(input: ActionInput) {
    log(`action:${input.operation}:${input.subscription_id}:rev-${input.revision}`);
    const receipt = await result(input.project_id, input.subscription_id, input.revision);
    setRows(old => old.map(r => r.subscription_id === input.subscription_id ? { ...r, revision: input.revision + 1, desired_state: input.operation === "remove" ? "removed" : input.operation === "stop" ? "stopped" : "running", operation_state: receipt.state,
      observed_state: receipt.state === "succeeded" ? input.operation === "remove" ? "absent" : input.operation === "stop" ? "stopped" : "running" : r.observed_state } : r));
    return receipt;
  }
  async function onAdd(input: AddInput) {
    log(`add:${input.project_id}`);
    const receipt = await result(input.project_id, subscriptionIds[7], 1);
    setRows(old => [...old, { ...demoSubscriptions()[0], subscription_id: subscriptionIds[7], project_id: input.project_id, name: input.name, x_handle: input.x_handle, operation_state: receipt.state, observed_state: receipt.state === "succeeded" ? "running" : "unknown", revision: 2, last_tweet_at: null }]);
    return receipt;
  }
  async function onRefresh() {
    log("refresh"); setRefreshing(true); setRefreshError(null);
    try { await wait(); if (scenario === "timeout") setRefreshError(fixtureError("UPSTREAM_TIMEOUT", "演示刷新超时，原列表与筛选已保留。")); }
    finally { setRefreshing(false); }
  }
  async function onReconcile(id: string) {
    log(`reconcile:${id}`); await wait();
    setRows(old => old.map(r => r.subscription_id === id ? { ...r, revision: r.revision + 1, observed_state: r.desired_state === "stopped" ? "stopped" : r.desired_state === "removed" ? "absent" : "running", operation_state: "succeeded" } : r));
  }
  async function onReconcileAdd(id: string) {
    log(`reconcile-add:${id}`); await wait();
    setRows(old => old.some(r => r.project_id === id) ? old.map(r => r.project_id === id ? { ...r, revision: r.revision + 1, observed_state: "running", operation_state: "succeeded" } : r) : [...old, { ...demoSubscriptions()[0], subscription_id: subscriptionIds[7], project_id: id, name: demoProject.name, x_handle: demoProject.x_handle, revision: 2, last_tweet_at: null }]);
  }
  const incomingSamples = demoIncomingActivities();
  function insertTweet() {
    const sample = incomingSamples[incoming]; if (!sample) return;
    setActivities(old => [sample, ...old]); setIncoming(old => old + 1);
    setRows(old => old.map(row => row.subscription_id === sample.subscription_id ? { ...row, last_tweet_at: sample.occurred_at } : row));
  }
  return <>
    <TrackingView mode="demo" role={role} capabilities={{ can_manage_tracking: role === "superadmin" }} subscriptions={screen === "data" ? rows : []} activities={screen === "data" ? activities : []} projects={[demoProject]} loading={screen === "loading"} refreshing={refreshing} error={screen === "error" ? fixtureError("UPSTREAM_UNAVAILABLE", "演示数据暂不可用，不回落为成功或运行中。") : refreshError} onAction={onAction} onAdd={onAdd} onRefresh={onRefresh} onReconcile={onReconcile} onReconcileAdd={onReconcileAdd} toolbarSlot={<>{toolbarSlot}<Button disabled={incoming >= incomingSamples.length || screen !== "data"} title="手动展示两条预置推文，不读取 X 或启动采集" onClick={insertTweet}>演示新推文</Button></>} />
    <details className={s.demoSettings}><summary>演示设置与测试</summary><div className={s.demoControls} aria-label="UI0 演示场景"><strong>演示控制台</strong><Select label="模拟角色" value={role} onChange={e => setRole(e.target.value as typeof role)}><option value="superadmin">superadmin · 模拟管理</option><option value="user">user · 只读</option></Select><Select label="注入回调结果" value={scenario} onChange={e => setScenario(e.target.value as Scenario)}><option value="success">确认完成</option><option value="denied">拒绝权限 / 403</option><option value="timeout">超时 / 待核实</option><option value="conflict">版本冲突 / 409</option><option value="pending">202 / 已受理</option><option value="unknown">unknown / 待核实</option></Select><Select label="页面状态" value={screen} onChange={e => { setScreen(e.target.value); setRefreshError(null); }}><option value="data">有数据</option><option value="loading">加载中</option><option value="empty">空列表</option><option value="error">加载错误</option></Select><span>回调次数 <output data-testid="callback-count">{calls.length}</output></span></div></details>
    <details className={s.callbackLog}><summary>演示回调记录（只含虚构标识）</summary><ol>{calls.map((call, i) => <li key={i}>{call}</li>)}</ol></details></>;
}
