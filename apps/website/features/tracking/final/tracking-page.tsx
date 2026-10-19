"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Alert, Badge, Button, DataTable, Dialog, EmptyState, Icon, Input, PageHeader, Panel, ScoreBadge, SearchInput, Select, Skeleton, ToastViewport, Toolbar, type TableColumn, type ToastMessage } from "@ikun/ui";
import { displayTime, emptyFilters, localMedia, paginate, relativeTime, selectPosts, statsFor, timeOf, validateAccount, type Account, type AccountInput, type Filters, type Grade, type Media, type Post } from "./model";
import s from "./tracking-page.module.css";

export interface TrackingPageProps {
  mode: "demo" | "live"; accounts: Account[]; posts: Post[]; loading?: boolean;
  onAdd?: (input: AccountInput) => Promise<void>; onRemove?: (key: string) => Promise<void>;
  live?: {historyAccounts?: Account[];connected?:boolean;accountMenu:ReactNode;canManage:boolean;refresh:()=>void;onOpenPost:(post:Post)=>void;manageActions:(account:Account)=>ReactNode;postActions?:(post:Post)=>ReactNode;addForm:(close:()=>void)=>ReactNode;pagination:ReactNode;server?:{filters:Filters;onFiltersChange:(next:Filters)=>void;matchedTotal:number|null;subscriptionCounts:{S:number;A:number;B:number}|null}};
}
const blankForm: AccountInput = { handle: "", name: "", note: "", grade: "A" };
const labels = { running: "监控中", starting: "启动中", stopping: "停止中", failed: "失败", stopped:"已停止", unknown: "待核实" };
function MediaPreview({ media, unknown }: { media: Media | null; unknown?:boolean }) {
  const source = localMedia(media?.src);
  return <div className={s.media} data-theme={media?.theme ?? "none"} role={media?.kind === "demo" ? "img" : undefined} aria-label={media?.kind === "demo" ? `演示配图：${media.title}` : undefined}>
    {media?.kind === "demo" ? <div><strong>{media.title}</strong><small>{media.caption}</small></div> : media?.kind === "image" && source ? <img src={source} alt={media.title} loading="lazy" /> : media?.kind === "video" && source ? <video src={source} controls preload="none" aria-label={media.title} /> : <small>{unknown ? "媒体信息未提供" : media ? "媒体暂不可用" : "无配图"}</small>}
  </div>;
}
function Metric({ kind, value }: { kind: "message" | "repeat" | "heart"; value: string }) {
  const paths = { message: "M20 11.5a8 8 0 0 1-8.5 8 9 9 0 0 1-4-.9L3 20l1.5-4a8 8 0 1 1 15.5-4.5z", repeat: "m17 2 4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3", heart: "M20.8 4.6a5.3 5.3 0 0 0-7.5 0L12 5.9l-1.3-1.3a5.3 5.3 0 1 0-7.5 7.5L12 21l8.8-8.9a5.3 5.3 0 0 0 0-7.5z" };
  return <span aria-label={`${{ message: "评论", repeat: "转发", heart: "喜欢" }[kind]} ${value}`}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d={paths[kind]} /></svg>{value}</span>;
}
export function TrackingPage({ mode, accounts, posts, loading = false, onAdd, onRemove, live }: TrackingPageProps) {
  const [now, setNow] = useState<number | null>(null), [localFilters, setFilters] = useState<Filters>(emptyFilters), [page, setPage] = useState(1);
  const [manager, setManager] = useState(false), [managerQuery, setManagerQuery] = useState("");
  const [adding, setAdding] = useState(false), [input, setInput] = useState<AccountInput>(blankForm), [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Account | null>(null), [busy, setBusy] = useState(false), flight = useRef(false);
  const [messages, setMessages] = useState<ToastMessage[]>([]), [restore, setRestore] = useState<"outside" | "inside" | null>(null);
  const manageTrigger = useRef<HTMLButtonElement>(null), showAdd = useRef<HTMLButtonElement>(null), managerSearch = useRef<HTMLDivElement>(null), deleteTrigger = useRef<HTMLElement | null>(null), cancelDelete = useRef<HTMLButtonElement>(null), handleInput = useRef<HTMLInputElement>(null), feed = useRef<HTMLElement>(null);
  useEffect(() => { setNow(Date.now()); const interval = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(interval); }, []);
  useEffect(() => { if (adding) handleInput.current?.focus(); }, [adding]);
  useEffect(() => {
    if (!restore || deleting || restore === "outside" && manager) return;
    const frame = requestAnimationFrame(() => {
      const target = restore === "outside" ? manageTrigger.current : deleteTrigger.current?.isConnected ? deleteTrigger.current : managerSearch.current?.querySelector('input') ?? showAdd.current;
      target?.focus(); setRestore(null);
    }); return () => cancelAnimationFrame(frame);
  }, [restore, manager, deleting]);
  const filters=live?.server?.filters??localFilters;
  const manageable = (mode === "demo" || live?.canManage === true) && !!onAdd && !!onRemove;
  const filtered = live?.server ? posts : selectPosts(accounts, posts, filters, now ?? 0), pagination = live?.server ? {...paginate([],1),items:posts} : paginate(filtered,page), stats = live?.server ? {today:live.server.matchedTotal??0,...(live.server.subscriptionCounts??{S:0,A:0,B:0})} : statsFor(accounts,posts,now??0);
  useEffect(() => { setPage(pagination.page); }, [pagination.page]);
  const notify = (title: string, tone: ToastMessage["tone"] = "info") => setMessages([{ id: "tracking-page-notice", title, tone }]);
  const reset = () => { if(live?.server)live.server.onFiltersChange(emptyFilters);else setFilters(emptyFilters); setPage(1); };
  const change = (patch: Partial<Filters>) => { if(live?.server)live.server.onFiltersChange({...filters,...patch});else setFilters(old => ({ ...old, ...patch })); setPage(1); };
  function closeManager() { if (deleting || busy) return; setManager(false); setAdding(false); setFormError(null); setRestore("outside"); }
  function closeDelete() { if (busy) return; setDeleting(null); setRestore("inside"); }
  async function addAccount() {
    if (!manageable || !onAdd || flight.current) return;
    const error = validateAccount(input, accounts); if (error) { setFormError(error); return; }
    flight.current = true; setBusy(true); setFormError(null);
    try { await onAdd({ ...input, handle: input.handle.trim().replace(/^@/, ""), name: input.name.trim(), note: input.note.trim() }); setAdding(false); setInput(blankForm); setManagerQuery(""); notify("演示添加成功：新账号暂时没有推文记录；未创建真实监控任务"); requestAnimationFrame(() => showAdd.current?.focus()); }
    catch { setFormError("本地演示操作失败，请核对账号列表后再试。"); }
    finally { flight.current = false; setBusy(false); }
  }
  async function removeAccount() {
    if (!manageable || !onRemove || !deleting || flight.current) return;
    flight.current = true; setBusy(true);
    try { await onRemove(deleting.ui_key); notify(mode === "live" ? "移除请求已持久受理，等待远端核验；历史与主页保持独立" : `「${deleting.name}」已从演示监控列表删除，未触碰真实监控`); setDeleting(null); setRestore("inside"); }
    catch { notify(mode === "live" ? "移除结果待核对，请查看命令与错误状态" : "本地演示删除失败，账号列表未确认变更。", "danger"); }
    finally { flight.current = false; setBusy(false); }
  }
  const managerRows = accounts.filter(account => `${account.note} ${account.name} ${account.handle}`.toLowerCase().includes(managerQuery.trim().toLowerCase())).sort((a, b) => ["S", "A", "B"].indexOf(a.grade ?? "") - ["S", "A", "B"].indexOf(b.grade ?? ""));
  const columns: TableColumn<Account>[] = [
    { key: "note", header: "备注", width: "25%", render: account => <span className={s.managerNote}>{account.note}</span> },
    { key: "project", header: "项目", width: "19%", render: account => <strong>{account.name}</strong> },
    { key: "handle", header: "X 账号", width: "20%", render: account => <span className={s.handle}>@{account.handle}</span> },
    { key: "grade", header: "评分", width: "9%", render: account => <ScoreBadge grade={account.grade} /> },
    { key: "status", header: "状态", width: "13%", render: account => <Badge tone={account.status === "running" ? "success" : account.status === "failed" ? "danger" : "neutral"}>{labels[account.status]}</Badge> },
    { key: "action", header: "操作", width: "14%", render: account => manageable ? <span>{live?.manageActions(account)}<Button size="sm" variant="danger" disabled={busy} aria-label={`删除 ${account.name}`} onClick={() => { deleteTrigger.current = document.activeElement as HTMLElement; setDeleting(account); }}>删除</Button></span> : <span>只读</span> },
  ];
  function goTo(next: number) { setPage(next); requestAnimationFrame(() => feed.current?.scrollIntoView({ block: "start" })); }
  return <section className={s.page} data-mode={mode} aria-label="猎手项目追踪页面">
    <div className={s.topbar}><span>控制台　/　<strong>猎手项目追踪</strong></span><div><span className={s.liveDot} />{mode === "demo" ? "页面演示中" : (live?.connected ? "实时来源已连接" : "实时来源未连接")}<time>{now ? new Date(now).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) : "—"}</time>{live?.accountMenu ?? <span className={s.admin} aria-label={mode === "demo" ? "演示身份" : "身份未接入"}>{mode === "demo" ? "A" : "?"}</span>}</div></div>
    <div className={s.content}>
      <PageHeader title="猎手项目追踪" description="已加入追踪的 S/A/B 级账号 · 最新推文按时间纵向排列" actions={<><Badge tone="warning">{mode === "demo" ? "● 演示数据 · UI 原型" : (live?.connected ? "实时来源已连接" : "实时来源未连接")}</Badge><Button disabled={loading || mode !== "demo" && !live} icon={<Icon name="refresh" />} title={mode === "live" ? "刷新监控状态与动态" : "重置筛选并刷新当前演示列表"} onClick={() => { reset(); if(live)live.refresh();else notify("已刷新演示列表 · 不会请求真实推文 API"); }}>刷新</Button></>} />
      <div className={s.stats} aria-label="追踪统计"><Panel className={s.stat}><span>{mode === "live" ? "匹配新推文" : "今日新推文"}</span><strong className={s.today} data-testid="today-count">{loading || !!live?.server && live.server.matchedTotal===null ? "—" : stats.today}</strong></Panel>{(["S", "A", "B"] as const).map(grade => <Panel className={s.stat} key={grade}><span><ScoreBadge grade={grade} /> 级项目</span><strong>{loading || !!live?.server && live.server.subscriptionCounts===null ? "—" : stats[grade]}</strong></Panel>)}<Button className={s.manageStat} ref={manageTrigger} aria-label={`监控账号总数 ${accounts.length}`} aria-haspopup="dialog" onClick={() => setManager(true)}><span>监控账号总数</span><strong data-testid="account-count">{loading ? "—" : accounts.length}</strong><Icon name="chevron" /></Button></div>
      <Toolbar className={s.filters} aria-label="推文搜索与筛选"><div className={s.search}><SearchInput label="搜索推文" value={filters.query} onValueChange={query => change({ query })} placeholder="搜索备注、项目、X 账号、推文内容…" /></div><div className={s.segment} role="group" aria-label="评级筛选">{(["all", "S", "A", "B"] as const).map(grade => <Button key={grade} size="sm" variant={filters.grade === grade ? "primary" : "ghost"} aria-pressed={filters.grade === grade} onClick={() => change({ grade })}>{grade === "all" ? (live?.server ? "S/A/B" : "全部") : `${grade} 级`}</Button>)}</div><Select label="时间范围" className={s.timeSelect} value={filters.hours} onChange={event => change({ hours: event.target.value as Filters["hours"] })}><option value="all">全部时间</option><option value="24">最近 24 小时</option><option value="168">最近 7 天</option></Select><label className={s.check}><input type="checkbox" disabled={mode === "live"} title={mode === "live" ? "重要标记未提供，当前不可用" : undefined} checked={filters.important} onChange={event => change({ important: event.target.checked })} />只看重要推文</label><Button variant="ghost" onClick={reset}>重置筛选</Button></Toolbar>
      <section ref={feed} aria-labelledby="tracking-feed-title" className={s.feedSection}><div className={s.feedHeading}><h2 id="tracking-feed-title">最新推文动态 <small>· 每页 {mode === "live" ? 20 : 6} 条</small></h2><span>匹配 {live?.server?.matchedTotal??filtered.length} 条{mode === "demo" ? "演示" : "全量匹配"}推文 · {mode === "live" ? "按发布时间排序 · 未知时回退接收时间" : "按最新时间排序"}</span></div><div className={s.feed}>
        {loading ? <Panel><Skeleton label="正在加载项目推文" lines={6} /></Panel> : pagination.items.map(post => { const account = (live?.historyAccounts ?? accounts).find(item => item.ui_key === post.account_key); if (!account) return null; if (mode === "live") return <article key={post.ui_key} className={s.tweetCompact} data-post={post.ui_key} data-published={post.published_at ?? ""} data-grade={account.grade} aria-label={`${account.name}的项目推文`}>
          <div className={s.compactHead}><ScoreBadge grade={account.grade} /><strong className={s.compactNote} title={account.name}>{account.name}</strong><span className={s.compactWho} title={account.note || undefined}>{account.note ? account.note + ' · ' : ''}@{account.handle}</span><span className={s.freshDot} data-old={!now || !Number.isFinite(timeOf(post)) || now - timeOf(post) >= 86400000} /><time className={s.compactTime} dateTime={post.published_at ?? undefined} title={displayTime(post.published_at)}>{relativeTime(post.published_at??post.received_at??null, now ?? 0)} · {displayTime(post.published_at??post.received_at??null)}</time><span className={s.compactActions}>{live?.canManage && live.postActions ? live.postActions(post) : null}<Button variant="ghost" size="sm" className={s.openPost} aria-label={`查看 ${account.name} 原文`} title="打开 X 原文" onClick={() => live?.onOpenPost(post)}><Icon name="arrow" /></Button></span></div>
          {post.translation_zh?.text ? <><p className={s.compactBody} title={post.translation_zh.text}>{post.translation_zh.text}</p><p className={s.compactOriginal} title={post.body}>原文：{post.body}</p></> : <p className={s.compactBody} title={post.body}>{post.body}</p>}
          {post.quoted_tweet ? <blockquote className={s.compactQuote} aria-label="被引用原推"><strong>{post.quoted_tweet.author_name} <span>@{post.quoted_tweet.author_handle}</span></strong> <span title={post.quoted_tweet.text}>{post.translation_zh?.quote || post.quoted_tweet.text}</span> <a href={post.quoted_tweet.url} target="_blank" rel="noopener noreferrer">原推</a></blockquote> : post.tweet_kind === 'quote' ? <small className={s.compactMissing}>原推正文未随已保存的推送提供</small> : null}
          {post.media_available ? <MediaPreview media={post.media} /> : null}
        </article>; return <article key={post.ui_key} className={s.tweet} data-post={post.ui_key} data-published={post.published_at ?? ""} data-grade={account.grade} aria-label={`${account.name}的${mode === "demo" ? "演示" : "项目"}推文`}>
          <div className={s.tweetNote}><span>备 注</span><strong>{account.note || "暂无备注"}</strong></div>
          <div className={s.identity}><span className={s.avatar} aria-hidden="true">{account.avatar}</span><div><strong title={account.name}>{account.name}</strong><small>@{account.handle}</small><ScoreBadge grade={account.grade} /></div></div>
          <div className={s.tweetContent}><div className={s.tweetTime}><span className={s.freshDot} data-old={!now || !Number.isFinite(timeOf(post)) || now - timeOf(post) >= 86400000} /><time dateTime={post.published_at ?? undefined} title={displayTime(post.published_at)}>{relativeTime(post.published_at??post.received_at??null, now ?? 0)}　·　{displayTime(post.published_at??post.received_at??null)}</time>{post.important && <span className={s.important}>◆ 重要</span>}</div><p title={post.body}>{post.body}</p>{post.quoted_tweet ? <blockquote className={s.quoteContext} aria-label="被引用原推"><strong>{post.quoted_tweet.author_name} <span>@{post.quoted_tweet.author_handle}</span></strong><p>{post.quoted_tweet.text}</p><a href={post.quoted_tweet.url} target="_blank" rel="noopener noreferrer">查看被引用原推</a></blockquote> : post.tweet_kind === 'quote' ? <small>原推正文未随已保存的推送提供</small> : null}<div className={s.metrics}><Metric kind="message" value={post.comments} /><Metric kind="repeat" value={post.reposts} /><Metric kind="heart" value={post.likes} /></div></div>
          <MediaPreview media={post.media} unknown={false} /><Button variant="ghost" size="sm" className={s.openPost} aria-label={`查看 ${account.name} 原文${mode === "demo" ? "（演示）" : ""}`} title="查看原文（演示推文无真实链接）" onClick={() => live ? live.onOpenPost(post) : notify(mode === "demo" ? "这是 UI 演示推文，不存在真实 X 原文链接。" : "尚未提供可核实的原文链接。") }><Icon name="arrow" /></Button>{live?.canManage && live.postActions ? live.postActions(post) : null}
        </article>; })}
        {!loading && !pagination.items.length && <div className={s.empty}><EmptyState title="暂无符合条件的推文" description={mode === "demo" ? "试着调整关键词、评级或时间筛选" : "未连接真实来源；当前没有符合条件的已授权推文。"} action={<Button onClick={reset}>清空筛选</Button>} /></div>}
      </div>{live ? live.pagination : <div className={s.feedFooter}><span>{filtered.length ? `显示 ${pagination.start}–${pagination.end} 条，共 ${filtered.length} 条` : "0 条"}</span><nav className={s.pager} aria-label="推文翻页"><Button size="sm" aria-label="上一页" disabled={pagination.page <= 1} onClick={() => goTo(pagination.page - 1)}>‹</Button>{Array.from({ length: pagination.totalPages }, (_, index) => <Button size="sm" key={index} aria-label={`第 ${index + 1} 页`} aria-current={pagination.page === index + 1 ? "page" : undefined} variant={pagination.page === index + 1 ? "primary" : "secondary"} onClick={() => goTo(index + 1)}>{index + 1}</Button>)}<Button size="sm" aria-label="下一页" disabled={pagination.page >= pagination.totalPages} onClick={() => goTo(pagination.page + 1)}>›</Button></nav></div>}</section>
      <footer className={s.footer}><span>{mode === "live" ? "本地 Tracking API · 数据来自本库 · 不代表真实平台已验收" : "UI 可点击演示　·　未接真实 NEW_TWEET API　·　未修改 tracking.db"}</span><span>{mode === "demo" ? "仅浏览器内存生效 · 刷新恢复初始数据" : "服务端全量筛选与计数 · 非 S/A/B 排除信息流"}</span></footer>
    </div>
    <div className={s.managerScope}><Dialog open={manager} title="监控账号管理" description={mode === "demo" ? "查看已加入追踪的 X 账号，演示添加 / 删除操作" : live?.canManage ? "管理已人工确认的项目 · 操作等待远端核验" : "已加入追踪的 X 账号 · 只读视图"} onOpenChange={open => { if (!open) closeManager(); }} pending={!!deleting || busy} initialFocusRef={showAdd} closeOnBackdrop><div className={s.managerToolbar}><div ref={managerSearch}><SearchInput label="搜索监控账号" value={managerQuery} onValueChange={setManagerQuery} placeholder="搜索备注、项目名或 X 账号…" /></div>{manageable && <Button ref={showAdd} variant="primary" onClick={() => { setAdding(true); setFormError(null); }}>＋ 添加监控账号</Button>}</div>
      {adding && (live ? live.addForm(()=>setAdding(false)) : <form className={s.addForm} method="post" action="/tracking" noValidate autoComplete="off" onSubmit={event => { event.preventDefault(); void addAccount(); }}><h3>新增监控账号（演示）</h3><div className={s.addGrid}><Input ref={handleInput} label="X 用户名" required maxLength={16} placeholder="@example_project" disabled={busy} value={input.handle} onChange={event => setInput(old => ({ ...old, handle: event.target.value }))} /><Input label="项目名称" required maxLength={50} placeholder="例如：Alpha Project" disabled={busy} value={input.name} onChange={event => setInput(old => ({ ...old, name: event.target.value }))} /><Input label="备注（优先显示）" required maxLength={80} placeholder="例如：重点关注主网上线" disabled={busy} value={input.note} onChange={event => setInput(old => ({ ...old, note: event.target.value }))} /><Select label="项目评分" required disabled={busy} value={input.grade} onChange={event => setInput(old => ({ ...old, grade: event.target.value as Grade }))}><option value="S">S 级</option><option value="A">A 级</option><option value="B">B 级</option></Select></div>{formError && <Alert tone="danger" title={formError} />}<div className={s.formActions}><Button disabled={busy} onClick={() => { setAdding(false); setInput(blankForm); setFormError(null); showAdd.current?.focus(); }}>取消</Button><Button type="submit" variant="primary" pending={busy}>确认添加（模拟）</Button></div></form>)}
      <p className={s.managerCount}>共 {accounts.length} 个监控账号 · 匹配 {managerRows.length} 个{mode === "demo" ? "（仅演示）" : ""}</p><DataTable caption="监控账号列表" columns={columns} rows={managerRows} rowKey={account => account.ui_key} minWidth={800} empty={<EmptyState title="没有匹配的监控账号" />} /><p className={s.managerNotice}>{mode === "live" ? "启停与移除等待远端核验；未知状态不能视为成功。不会修改主页项目。" : "本窗口只模拟管理界面；不会修改真实监控。"}</p>
    </Dialog></div>
    <Dialog open={!!deleting} title="确认删除账号？" description={mode === "live" ? "请求移除此订阅；远端核验前保留，推文历史和主页项目不受影响。" : deleting ? `确定从演示监控列表删除「${deleting.name}」（@${deleting.handle}）吗？对应推文将从本页演示信息流隐藏，实际监控和数据库不受影响。` : ""} pending={busy} initialFocusRef={cancelDelete} onOpenChange={open => { if (!open) closeDelete(); }} footer={<><Button ref={cancelDelete} disabled={busy} onClick={closeDelete}>取消</Button><Button variant="danger" pending={busy} onClick={() => void removeAccount()}>{mode === "live" ? "确认请求移除" : "确认删除（演示）"}</Button></>}><span>{mode === "live" ? "此操作只影响当前订阅。" : "仅确认当前演示账号。"}</span></Dialog>
    <ToastViewport messages={messages} onDismiss={() => setMessages([])} />
  </section>;
}
