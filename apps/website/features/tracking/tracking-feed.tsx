"use client";
import { useState } from "react";
import { Badge, Button, EmptyState, ErrorState, Input, Panel, SearchInput, Select, Skeleton, Toolbar } from "@ikun/ui";
import type { ActivityDTO, PublicError, SubscriptionDTO } from "./types";
import { activityTime, formatTime, safeTweetURL, trackingActivities } from "./view-model";
import s from "./tracking.module.css";

interface Props {
  subscriptions: SubscriptionDTO[];
  activities: ActivityDTO[];
  mode: "demo" | "live";
  loading?: boolean;
  refreshing?: boolean;
  error?: PublicError | null;
  onOpenTweet: (activity: ActivityDTO) => void;
}
export function TrackingFeed({ subscriptions, activities, mode, loading, refreshing, error, onOpenTweet }: Props) {
  const [project, setProject] = useState("all"), [query, setQuery] = useState("");
  const [sort, setSort] = useState("latest"), [day, setDay] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [frozen, setFrozen] = useState<ActivityDTO[] | null>(null);
  const all = trackingActivities(activities, subscriptions);
  const shown = trackingActivities(frozen ?? activities, subscriptions, project, query, sort, day);
  const pending = frozen ? trackingActivities(activities, subscriptions, project, query, sort, day).filter(a => !frozen.some(old => old.activity_id === a.activity_id)).length : 0;
  const clear = () => { setProject("all"); setQuery(""); setDay(""); };
  return <Panel className={`ik-panel--table ${s.feed}`} aria-label="项目推文动态" title="推文事件中心" description="只看你已跟踪项目的推文，点击记录展开原文" actions={<div className={s.feedActions}><Badge>{shown.length} 条推文</Badge><Button size="sm" disabled={!all.length} onClick={() => setFrozen(frozen ? null : [...activities])}>{frozen ? "恢复更新" : "暂停更新"}</Button></div>} aria-busy={!!loading || !!refreshing}>
      <Toolbar className={s.feedFilters}><Select label="动态项目筛选" value={project} onChange={e => setProject(e.target.value)}><option value="all">全部项目动态</option>{subscriptions.map(row => <option key={row.subscription_id} value={row.project_id}>{row.name}{row.desired_state === "removed" ? " · 已移除历史" : ""}</option>)}</Select><div className={s.feedSearch}><SearchInput label="搜索推文内容" value={query} onValueChange={setQuery} placeholder="搜索项目 / X 账号 / 推文关键词" /></div><Input label="历史推文日期" type="date" value={day} onChange={e => setDay(e.target.value)} /><Select label="推文排序" value={sort} onChange={e => setSort(e.target.value)}><option value="latest">最新优先</option><option value="oldest">最早优先</option></Select>{(project !== "all" || query || day) && <Button size="sm" onClick={clear}>重置筛选</Button>}</Toolbar>
      <div className={s.feedStatus}><span>{refreshing ? "保留已加载推文 · 刷新中" : frozen ? "动态更新已暂停" : "按推文时间排列"}</span><span>北京时间 · 共 {shown.length} 条</span></div>
      {frozen && <Button className={s.pendingFeed} onClick={() => setFrozen(null)}>已暂停 · {pending} 条新动态 · 点击恢复</Button>}
      <div className={s.feedBody}>
        {loading ? <div className={s.feedLoading}><Skeleton label="正在加载项目推文" lines={6} /></div> : error && !all.length ? <ErrorState title={error.code} requestId={error.request_id} description={error.message} /> : <>
          {shown.length > 0 && <><div className={s.eventHead} aria-hidden="true"><span>时间</span><span>项目 / X 账号</span><span>最新推文摘要</span><span>查看</span></div><ul className={s.eventList} aria-label="已跟踪项目推文列表">
            {shown.slice(0, 100).map(activity => { const when = activityTime(activity), open = expanded === activity.activity_id; return <li key={activity.activity_id}><details open={open} className={s.event}><summary data-activity={activity.activity_id} aria-controls={`tweet-${activity.activity_id}`} onClick={event => { event.preventDefault(); setExpanded(open ? null : activity.activity_id); }}><time dateTime={when.at} title={when.receivedOnly ? "发生时间未知，此处为接收时间" : "推文发布时间"}>{formatTime(when.at).replace(/^\d{4}\//, "")}{when.receivedOnly && <small>接收时间</small>}</time><span className={s.eventProject}><strong>{activity.project_name}</strong><small>@{activity.x_handle}</small></span><span className={s.eventPreview}><span className={s.eventDot} aria-hidden="true" />{activity.text.replace(/\n/g, " ")}</span><span className={s.eventChevron} aria-hidden="true">{open ? "⌄" : "›"}</span></summary><div className={s.eventDetail} id={`tweet-${activity.activity_id}`}>
              <div className={s.eventIdentity}><div><strong>{activity.project_name}</strong><span>@{activity.x_handle}</span>{mode === "demo" && <Badge tone="warning">演示推文</Badge>}</div><time dateTime={when.at}>{when.receivedOnly ? "发生时间未知 · 接收于 " : "发布于 "}{formatTime(when.at)}（北京时间）</time></div>
              <div className={s.eventColumns}><div><h3>推文原文</h3><p className={s.eventText}>{activity.text}</p><div className={s.eventLinks}><Button size="sm" variant="ghost" onClick={() => onOpenTweet(activity)}>查看全文 ↗</Button>{mode === "demo" ? <span>虚构推文，不提供原文链接</span> : safeTweetURL(activity.url) ? <a href={safeTweetURL(activity.url)!} target="_blank" rel="noreferrer noopener">查看 X 原文 ↗</a> : <span>原文链接不可用</span>}</div></div><div className={s.translation}><h3>中文译文与摘要</h3><p>尚未接入，当前展示项目推文原文。</p></div></div>
            </div></details></li>; })}
          </ul></>}
          {!shown.length && <EmptyState title={query || day ? "没有匹配的推文" : "暂无推文动态"} description={query || day ? "调整关键词或日期，查看其他项目动态。" : mode === "demo" ? "该项目暂未加载推文，选择其他项目体验。" : "等待接入方提供已跟踪项目的推文。"} action={project !== "all" || query || day ? <Button onClick={clear}>查看全部项目</Button> : undefined} />}
        </>}
      </div>
      <footer className={s.tableFooter}><span>已停止或移除项目可保留历史推文</span><span>当前页最多100条 · {mode === "demo" ? "演示数据" : "已加载记录"}</span></footer>
    </Panel>;
}
