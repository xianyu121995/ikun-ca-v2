"use client";
import { useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, DataTable, Dialog, EmptyState, ErrorState, PageHeader, Panel, SearchInput, Select, Toolbar, type TableColumn } from "@ikun/ui";
import type { ActivityDTO, AddInput, CommandDTO, MonitorOperation, PublicError, SubscriptionDTO, TrackingProps } from "./types";
import { activityTime, canWrite, formatTime, isUnverified, mutationBlock, operationLabel, primaryOperation, projectRows, publicError, safeTweetURL, stateLabels, toAction, trackingActivities, validateAdd, validateReceipt } from "./view-model";
import s from "./tracking.module.css";
import { TrackingFeed } from "./tracking-feed";

function State({ kind, value }: { kind: keyof typeof stateLabels; value: string }) {
  const label = (stateLabels[kind] as Record<string, string>)[value] ?? "未知";
  return <Badge tone={value === "unknown" || value === "failed" ? "warning" : value === "connected" || value === "succeeded" ? "success" : "neutral"} data-state={`${kind}:${value}`}>{label}</Badge>;
}

export function TrackingView(props: TrackingProps) {
  const { subscriptions, activities, mode } = props;
  const [query, setQuery] = useState(""), [status, setStatus] = useState("all"), [sort, setSort] = useState("latest"), [includeRemoved, setIncludeRemoved] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null), [tweet, setTweet] = useState<ActivityDTO | null>(null);
  const [confirmation, setConfirmation] = useState<SubscriptionDTO | null>(null), [adding, setAdding] = useState(false);
  const [projectId, setProjectId] = useState(""), [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<Set<string>>(new Set()), flight = useRef(new Set<string>());
  const [receipts, setReceipts] = useState<Record<string, { value: CommandDTO; revision: number }>>({});
  const [uncertain, setUncertain] = useState<Record<string, { revision: number; queried: boolean }>>({});
  const [pendingAdd, setPendingAdd] = useState<{ project_id: string; command_id: string | null } | null>(null);
  const [notice, setNotice] = useState<string | null>(null), [actionError, setActionError] = useState<PublicError | null>(null), [formError, setFormError] = useState<string | null>(null);
  const [managing, setManaging] = useState(false);
  const management = useRef<HTMLDivElement>(null);
  const [restoreFocus, setRestoreFocus] = useState(false);
  const trigger = useRef<HTMLElement | null>(null), searchWrapper = useRef<HTMLDivElement>(null);
  const cancelRemove = useRef<HTMLButtonElement>(null), cancelAdd = useRef<HTMLButtonElement>(null);
  const manageable = canWrite(props), rows = projectRows(subscriptions, query, status, sort, includeRemoved).slice(0, 100);
  useEffect(() => { if (pendingAdd && subscriptions.some(r => r.project_id === pendingAdd.project_id && ["succeeded", "failed"].includes(r.operation_state))) setPendingAdd(null); }, [subscriptions, pendingAdd]);
  const detail = subscriptions.find(r => r.subscription_id === detailId);
  const receipt = (row: SubscriptionDTO) => receipts[row.subscription_id]?.revision === row.revision ? receipts[row.subscription_id].value : undefined;
  const uncertainNow = (row: SubscriptionDTO) => isUnverified(row, uncertain[row.subscription_id]);
  const block = (row: SubscriptionDTO) => uncertainNow(row) ? "结果待核实，请先查询原回执" : mutationBlock(row, busy.has(row.subscription_id), receipt(row));
  const begin = (key: string) => { if (flight.current.has(key)) return false; flight.current.add(key); setBusy(new Set(flight.current)); return true; };
  const end = (key: string) => { flight.current.delete(key); setBusy(new Set(flight.current)); };
  const rememberFocus = () => { trigger.current = document.activeElement as HTMLElement; };
  // Page-level fallback only; modal semantics and focus trapping belong to shared Dialog.
  const closeWithFocus = (close: () => void) => { setRestoreFocus(true); close(); };
  useEffect(() => {
    if (!restoreFocus || detailId || tweet || confirmation || adding) return;
    // Shared Dialog closes in its effect; wait until the background is no longer inert.
    const frame = requestAnimationFrame(() => {
      const previous = trigger.current;
      const available = previous?.isConnected && !previous.matches(':disabled') && previous.getClientRects().length > 0;
      (available ? previous : searchWrapper.current?.querySelector('input'))?.focus();
      setRestoreFocus(false);
    });
    return () => cancelAnimationFrame(frame);
  }, [restoreFocus, detailId, tweet, confirmation, adding]);
  const openManagement = () => { setManaging(true); requestAnimationFrame(() => management.current?.scrollIntoView({ block: "start" })); };

  async function run(row: SubscriptionDTO, operation: MonitorOperation) {
    if (!manageable || !props.onAction || block(row) || !begin(row.subscription_id)) return;
    setActionError(null); setNotice(null);
    try {
      const result = await props.onAction(toAction(row, operation));
      if (!validateReceipt(result, row)) throw { code: "INTERNAL_ERROR", message: "回执身份不匹配，请查询原操作结果。", request_id: "未提供", retryable: false };
      setReceipts(old => ({ ...old, [row.subscription_id]: { value: result, revision: row.revision } }));
      if (result.state === "unknown") setUncertain(old => ({ ...old, [row.subscription_id]: { revision: row.revision, queried: false } }));
      setNotice(result.state === "unknown" ? "结果待核实，请查询原回执；不要重复提交。" : result.state === "succeeded" ? "收到完成回执，远端观测仍以数据投影为准。" : result.state === "failed" ? "操作失败，请查看公开错误码与请求编号。" : "命令已持久受理，等待业务完成确认。受理不代表监控成功。");
      if (result.state === "failed") setActionError({ code: result.error_code ?? "INTERNAL_ERROR", message: "命令执行失败，请核对原回执。", request_id: result.request_id, retryable: false });
      if (operation === "remove") closeWithFocus(() => setConfirmation(null));
    } catch (error) {
      const info = publicError(error); setActionError(info);
      if (["UPSTREAM_TIMEOUT", "INTERNAL_ERROR"].includes(info.code)) setUncertain(old => ({ ...old, [row.subscription_id]: { revision: row.revision, queried: false } }));
    } finally { end(row.subscription_id); }
  }
  async function reconcile(row: SubscriptionDTO) {
    if (!props.onReconcile || !begin(`read:${row.subscription_id}`)) return;
    try { await props.onReconcile(row.subscription_id, receipt(row)?.command_id ?? null); setUncertain(old => old[row.subscription_id] ? { ...old, [row.subscription_id]: { ...old[row.subscription_id], queried: true } } : old); setNotice("已查询原回执，状态以调用方提供的最新投影为准。"); }
    catch (error) { setActionError(publicError(error)); }
    finally { end(`read:${row.subscription_id}`); }
  }
  function rowActions(row: SubscriptionDTO, includeDetails = true) {
    const reason = block(row);
    const unknown = uncertainNow(row) || row.operation_state === "unknown" || row.observed_state === "unknown" || receipt(row)?.state === "unknown";
    return <div className={s.actions}>
      {unknown ? <Button size="sm" onClick={() => void reconcile(row)} disabled={!props.onReconcile || busy.has(`read:${row.subscription_id}`)} title={!props.onReconcile ? "未提供原回执查询回调" : "仅查询原操作，不重复写入"}>查询原回执</Button> : manageable && row.desired_state !== "removed" ? <>
        <Button size="sm" disabled={!!reason || !props.onAction} title={reason ?? (!props.onAction ? "未提供操作回调" : "")} onClick={() => void run(row, primaryOperation(row))}>{busy.has(row.subscription_id) ? "提交中…" : operationLabel(primaryOperation(row))}</Button>
        <Button size="sm" disabled={!!reason || !props.onAction} title={reason ?? (!props.onAction ? "未提供移除回调" : "仅移除监控，不影响主页")} onClick={() => { rememberFocus(); setActionError(null); setDetailId(null); setConfirmation(row); }}>移除</Button>
      </> : <span className={s.subtle}>{row.desired_state === "removed" ? "已移除" : "只读"}</span>}
      {includeDetails && <Button size="sm" aria-label={`查看 ${row.name} 详情`} onClick={() => { rememberFocus(); setDetailId(row.subscription_id); }}>详情 ↗</Button>}
    </div>;
  }
  async function add() {
    if (!manageable || !props.onAdd || pendingAdd || !begin("add")) return;
    const target = props.projects?.find(p => p.project_id === projectId);
    const input: AddInput = { project_id: projectId, name: target?.name ?? "", x_handle: target?.x_handle ?? "", x_user_id: null, notes: "", confirmed: confirmed as true };
    const error = validateAdd(input);
    if (error) { setFormError(error); end("add"); return; }
    setFormError(null); setActionError(null);
    try {
      const result = await props.onAdd(input);
      if (!validateReceipt(result) || result.project_id !== input.project_id) throw { code: "INTERNAL_ERROR", message: "加入结果待核实，请查原回执。", request_id: "未提供", retryable: false };
      if (["accepted", "pending", "running", "unknown"].includes(result.state)) setPendingAdd({ project_id: input.project_id, command_id: result.command_id });
      setNotice(`加入请求：${stateLabels.operation[result.state]}；不会加入或恢复主页。`); closeWithFocus(() => setAdding(false));
    } catch (error) { const info = publicError(error); setActionError(info); if (["UPSTREAM_TIMEOUT", "INTERNAL_ERROR"].includes(info.code)) { setPendingAdd({ project_id: input.project_id, command_id: null }); closeWithFocus(() => setAdding(false)); } }
    finally { end("add"); }
  }
  const displayError = actionError ?? props.error;
  const errorView = (error: PublicError) => <ErrorState title={error.code} requestId={error.request_id} description={`${error.message}${error.code === "VERSION_CONFLICT" ? " 版本冲突：请刷新后核对最新版本，保留当前筛选，不自动覆盖。" : ""} ${error.retryable ? "可由调用方核实重试。" : "不自动重试。"}`} />;
  const columns: TableColumn<SubscriptionDTO>[] = [
    { key: "project", header: "项目 / X 账号", width: "230px", render: row => <Button variant="ghost" className={s.identity} data-subscription={row.subscription_id} onClick={() => { rememberFocus(); setDetailId(row.subscription_id); }}><span className={s.avatar}>{row.name.slice(0, 1)}</span><span><strong>{row.name}</strong><small>@{row.x_handle}</small></span></Button> },
    { key: "desired", header: "目标状态", render: row => <State kind="desired" value={row.desired_state} /> },
    { key: "observed", header: "远端观测", render: row => <State kind="observed" value={row.observed_state} /> },
    { key: "operation", header: "操作回执", render: row => <State kind="operation" value={uncertainNow(row) ? "unknown" : receipt(row)?.state ?? row.operation_state} /> },
    { key: "connection", header: "来源连接", render: row => <State kind="connection" value={row.connection} /> },
    { key: "tweet", header: "最近推文", render: row => <span className={s.time}>{formatTime(row.last_tweet_at)}</span> },
    { key: "actions", header: "操作", render: row => rowActions(row) },
  ];
  const empty = <EmptyState title={query || status !== "all" ? "没有匹配的监控项目" : "尚无监控项目"} description={mode === "live" ? "等待接入方提供已授权的数据。" : "选择其他筛选，或明确加入监控。"} action={query || status !== "all" ? <Button onClick={() => { setQuery(""); setStatus("all"); }}>清除筛选</Button> : undefined} />;
  return <section className={s.page} aria-label="项目监控页面" data-mode={mode}>
    <div className={s.breadcrumb}><span>猎手工作台 / 项目监控</span><Badge tone={mode === "demo" ? "warning" : "neutral"}>{mode === "demo" ? "演示数据 · 非真实监控" : "只读视图 · 未接入服务"}</Badge></div>
    <PageHeader eyebrow="PROJECT FEED" title="项目推文" description="你跟踪的项目，最新推文集中在这里。" actions={<>{props.toolbarSlot}<Button pending={!!props.refreshing} disabled={!props.onRefresh || props.loading} title={!props.onRefresh ? "未提供刷新回调" : "刷新当前列表和推文"} onClick={() => { void props.onRefresh?.().catch(error => setActionError(publicError(error))); }}>{props.refreshing ? "刷新中…" : "刷新"}</Button><Button aria-expanded={managing} aria-controls="tracking-management" onClick={() => managing ? setManaging(false) : openManagement()}>监控管理</Button></>} />
    <div className={s.notices}>{mode === "demo" ? <p className={s.demoNotice}><Badge tone="warning">演示模式</Badge><span>项目、推文与权限均为虚构 · 操作仅在本页生效</span></p> : <Alert title="真实服务尚未接入">当前没有真实身份与监控数据，管理能力默认关闭。</Alert>}
      {displayError && (subscriptions.length > 0 || actionError) && errorView(displayError)}
      {notice && <Alert title={notice} />}
      {pendingAdd && <Alert tone="warning" title="加入请求仍待核实，暂不允许重复加入" action={<Button size="sm" disabled={!props.onReconcileAdd || busy.has("read:add")} onClick={() => { if (props.onReconcileAdd && begin("read:add")) void props.onReconcileAdd(pendingAdd.project_id, pendingAdd.command_id).catch(error => setActionError(publicError(error))).finally(() => end("read:add")); }}>查询加入回执</Button>} />}
    </div>
    <div className={s.summary}><span><strong>{subscriptions.filter(r => r.desired_state !== "removed").length}</strong> 个已跟踪项目</span><span><strong>{trackingActivities(activities, subscriptions).length}</strong> 条已加载推文</span><span>北京时间</span></div>
    <TrackingFeed subscriptions={subscriptions} activities={activities} mode={mode} loading={!!props.loading} refreshing={!!props.refreshing} error={props.error ?? null} onOpenTweet={activity => { rememberFocus(); setTweet(activity); }} />
    <div ref={management} id="tracking-management" hidden={!managing} className={s.management}><Panel className="ik-panel--table" aria-label="持续监控项目" title={<>监控项目 <Badge>{rows.length}</Badge></>} description={props.refreshing ? "保留旧数据 · 刷新中" : "目标、远端观测、操作与连接分别展示"} actions={<><Button size="sm" onClick={() => setManaging(false)}>收起管理</Button>{manageable && <Button size="sm" variant="primary" disabled={!props.onAdd || props.loading || !!pendingAdd} title={pendingAdd ? "加入结果待核实，禁止重复提交" : !props.onAdd ? "未提供加入监控回调" : "选择已注册项目"} onClick={() => { rememberFocus(); setAdding(true); setProjectId(""); setConfirmed(false); setFormError(null); setActionError(null); }}>＋ 加入监控</Button>}</>}>
      <Toolbar className={s.filters}><div className={s.search} ref={searchWrapper}><SearchInput label="搜索项目、X 账号或标识" value={query} onValueChange={setQuery} placeholder="搜索项目 / X 账号 / ID" /></div><Select label="状态筛选" value={status} onChange={e => setStatus(e.target.value)}><option value="all">全部状态</option><option value="running">远端确认运行</option><option value="pending">处理中</option><option value="unknown">待核实</option><option value="failed">操作失败</option><option value="stopped">远端停止</option></Select><Select label="排序" value={sort} onChange={e => setSort(e.target.value)}><option value="latest">最近推文</option><option value="updated">状态更新时间</option><option value="name">项目名称</option></Select><label className={s.check}><input type="checkbox" checked={includeRemoved} onChange={e => setIncludeRemoved(e.target.checked)} />包括已移除</label></Toolbar>
      <DataTable caption="持续监控项目列表" columns={columns} rows={rows} rowKey={row => row.subscription_id} loading={!!props.loading} refreshing={!!props.refreshing} minWidth={1120} empty={empty} error={props.error && !subscriptions.length ? errorView(props.error) : undefined} />
      <footer className={s.tableFooter}><span>显示 {rows.length} 条 · 当前页最多100条</span><span>左右滑动查看完整列 · 北京时间</span></footer>
    </Panel></div>
    <Dialog open={!!detail} title="项目监控详情" onOpenChange={open => { if (!open) closeWithFocus(() => setDetailId(null)); }}>{detail && <><div className={s.detailHeading}><span className={s.avatar}>{detail.name.slice(0, 1)}</span><div><h3>{detail.name}</h3><span>@{detail.x_handle}</span></div></div><dl className={s.facts}><div><dt>subscription_id</dt><dd data-testid="subscription-id">{detail.subscription_id}</dd></div><div><dt>project_id</dt><dd data-testid="project-id">{detail.project_id}</dd></div><div><dt>revision</dt><dd>{detail.revision}</dd></div>{(["desired", "observed", "operation", "connection"] as const).map((kind, i) => <div key={kind}><dt>{["目标状态", "远端观测", "操作回执", "来源连接"][i]}</dt><dd><State kind={kind} value={kind === "desired" ? detail.desired_state : kind === "observed" ? detail.observed_state : kind === "connection" ? detail.connection : uncertainNow(detail) ? "unknown" : receipt(detail)?.state ?? detail.operation_state} /></dd></div>)}<div><dt>最近推文</dt><dd>{formatTime(detail.last_tweet_at)}</dd></div></dl><p className={s.subtle}>{detail.notes || "暂无备注"}</p><div className={s.modalActions}>{rowActions(detail, false)}<Button onClick={() => closeWithFocus(() => setDetailId(null))}>关闭</Button></div></>}</Dialog>
    <Dialog open={!!confirmation} title="移除项目监控？" pending={!!confirmation && busy.has(confirmation.subscription_id)} initialFocusRef={cancelRemove} onOpenChange={open => { if (!open) closeWithFocus(() => setConfirmation(null)); }} footer={<><Button ref={cancelRemove} disabled={!!confirmation && busy.has(confirmation.subscription_id)} onClick={() => closeWithFocus(() => setConfirmation(null))}>取消</Button><Button variant="danger" disabled={!confirmation || !manageable || !!block(confirmation)} onClick={() => { if (confirmation) void run(confirmation, "remove"); }}>确认移除监控</Button></>}><p>确认移除 {confirmation?.name} 的监控订阅？</p><p className={s.subtle}>本操作仅移除监控，不改变项目的主页成员状态；推文历史保留。</p>{actionError && errorView(actionError)}</Dialog>
    <Dialog open={adding} title="加入项目监控" pending={busy.has("add")} initialFocusRef={cancelAdd} onOpenChange={open => { if (!open) closeWithFocus(() => setAdding(false)); }} footer={<><Button ref={cancelAdd} disabled={busy.has("add")} onClick={() => closeWithFocus(() => setAdding(false))}>取消</Button><Button variant="primary" disabled={!manageable || !props.onAdd || !confirmed || !projectId || busy.has("add")} pending={busy.has("add")} onClick={() => void add()}>{busy.has("add") ? "提交中…" : "确认加入监控"}</Button></>}><p className={s.subtle}>选择已注册的项目并明确确认；加入监控不会将项目加入主页。</p><Select label="选择已注册项目" value={projectId} onChange={e => setProjectId(e.target.value)}><option value="">请选择</option>{props.projects?.map(p => <option key={p.project_id} value={p.project_id} disabled={subscriptions.some(r => r.project_id === p.project_id && r.desired_state !== "removed")}>{p.name}</option>)}</Select>{projectId && <code className={s.code}>{projectId}</code>}<label className={s.check}><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />我明确确认加入监控（不加入主页）</label>{formError && <Alert tone="danger" title={formError} />}{actionError && errorView(actionError)}</Dialog>
    <Dialog open={!!tweet} title="推文全文" onOpenChange={open => { if (!open) closeWithFocus(() => setTweet(null)); }} footer={<Button onClick={() => closeWithFocus(() => setTweet(null))}>关闭</Button>}>{tweet && <><h3>{tweet.project_name}</h3><p className={s.fullTweet}>{tweet.text}</p><p className={s.subtle}>{activityTime(tweet).receivedOnly ? "发生时间未知，展示接收时间" : "发生时间"} · {formatTime(activityTime(tweet).at)}（北京时间）</p>{mode === "demo" ? <p className={s.subtle}>虚构推文，不提供原文链接。</p> : safeTweetURL(tweet.url) ? <a href={safeTweetURL(tweet.url)!} rel="noreferrer noopener" target="_blank">查看 X 原文 ↗</a> : <p>原文链接不可用</p>}</>}</Dialog>
  </section>;
}
