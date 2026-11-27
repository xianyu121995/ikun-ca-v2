import React from "react";
import { Alert, Badge, EmptyState, PageHeader, Panel } from "@ikun/ui";
import { chainLabel, chainSide, EMPTY_COPY, groupEvents, LIST_PAGE_SIZE, LIST_PREVIEW, type HackathonEvent, type HackathonProject, type HackathonSnapshot, type ListFocus, type Phase, type ProjectListKind, type SnapshotLoad } from "../../lib/hackathon-snapshot";
import { officialHandle } from "../../lib/hackathon-watches";
import { WatchButton } from "./watch-button";

const PHASE_LABEL: Record<Phase, string> = { live: "进行中", upcoming: "即将开始", ended: "已结束", unknown: "时间未明" };
const PHASE_TONE: Record<Phase, "success" | "info" | "neutral" | "warning"> = { live: "success", upcoming: "info", ended: "neutral", unknown: "warning" };

export function HackathonBoard({ load, now, focus = null, csrf = "" }: { load: SnapshotLoad; now: string; focus?: ListFocus | null; csrf?: string }) {
  if (!load.ok) {
    return <div className="hk-board">
      <Header />
      <EmptyState title="监控还没有可展示的快照" description={EMPTY_COPY[load.reason]} />
    </div>;
  }
  const failed = load.snapshot.sources.filter(source => !source.ok);
  const changes = (load.snapshot.changes ?? []).slice(-12).reverse();
  return <div className="hk-board">
    <Header checkedAt={load.snapshot.generated_at_beijing} />
    <ChainFilter />
    <Alert tone="warning" title="这里看不到全部投稿">{EMPTY_COPY.notEverything}</Alert>
    {changes.length > 0 && <section className="hk-section" aria-labelledby="hk-changes">
      <h2 id="hk-changes">最近变化</h2>
      <ul className="hk-changes">{changes.map(change => {
        const side = chainSide(changeSideInput(change, load.snapshot));
        const label = chainLabel(changeSideInput(change, load.snapshot));
        return <li key={change.id} className="hk-change" data-ecosystem={side}><strong>{change.label}</strong>{label && <span className={`hk-chain hk-chain-${side}`}>{label}</span>} {change.event}{change.at_beijing ? ` · ${change.at_beijing} 北京时间` : ""}</li>;
      })}</ul>
      <p className="hk-changes-none">这条链没有最近变化。</p>
    </section>}
    {failed.length > 0 && <Alert tone="warning" title="有来源这次没有核对成功">{failed.map(source => <p key={source.id}>{source.id}：{source.error || "失败"}。上次成功的内容会保留。</p>)}</Alert>}
    <Ecosystem id="bsc" title="BSC" note="BNB Chain / BSC" events={load.snapshot.events.filter(event => chainSide(event) === "bsc" || chainSide(event) === "both")} now={now} focus={focus} csrf={csrf} />
    <Ecosystem id="sol" title="SOL" note="Solana" events={load.snapshot.events.filter(event => chainSide(event) === "sol" || chainSide(event) === "both")} now={now} focus={focus} csrf={csrf} />
    <Ecosystem id="unknown" title="链未标明" note="来源没有写出链" events={load.snapshot.events.filter(event => chainSide(event) === "unknown")} now={now} focus={focus} csrf={csrf} />
  </div>;
}

function changeSideInput(change: NonNullable<HackathonSnapshot["changes"]>[number], snapshot: HackathonSnapshot) {
  if (change.chain || change.ecosystem) return change;
  const matches = snapshot.events.filter(event => event.title === change.event);
  return matches.length === 1 ? matches[0] : {};
}

function ChainFilter() {
  return <fieldset className="hk-filter">
    <legend>按链筛选</legend>
    <label htmlFor="hk-chain-all"><input id="hk-chain-all" type="radio" name="hk-chain" defaultChecked /> 全部</label>
    <label htmlFor="hk-chain-bsc"><input id="hk-chain-bsc" type="radio" name="hk-chain" /> BSC</label>
    <label htmlFor="hk-chain-sol"><input id="hk-chain-sol" type="radio" name="hk-chain" /> SOL</label>
  </fieldset>;
}

function Ecosystem({ id, title, note, events, now, focus, csrf }: { id: "bsc" | "sol" | "unknown"; title: string; note: string; events: HackathonEvent[]; now: string; focus: ListFocus | null; csrf: string }) {
  if (id === "unknown" && !events.length) return null;
  const groups = groupEvents(events, new Date(now));
  return <section className="hk-ecosystem" data-ecosystem={id} aria-labelledby={`hk-${id}`}>
    <h2 id={`hk-${id}`}><span className={`hk-chain hk-chain-${id}`}>{title}</span>{note}</h2>
    <div className="hk-section" aria-labelledby={`hk-${id}-current`}>
      <h3 id={`hk-${id}-current`}>进行中与即将开始</h3>
      {groups.current.length ? groups.current.map(event => <EventCard key={event.id} event={event} focus={focus} csrf={csrf} />) : <EmptyState title="没有进行中的黑客松" description={EMPTY_COPY.noCurrent} />}
    </div>
    <div className="hk-section" aria-labelledby={`hk-${id}-archive`}>
      <h3 id={`hk-${id}-archive`}>已结束（归档）</h3>
      <p className="hk-section-note">归档会一直保留。监控不会在某一届结束后停掉，也不会把结束当成删除。</p>
      {groups.archive.length ? groups.archive.map(event => <EventCard key={event.id} event={event} focus={focus} csrf={csrf} />) : <EmptyState title="归档还是空的" description={EMPTY_COPY.noArchive} />}
    </div>
    {(groups.relatedCurrent.length > 0 || groups.relatedArchive.length > 0) && <div className="hk-section" aria-labelledby={`hk-${id}-related`}>
      <h3 id={`hk-${id}-related`}>相关官方活动</h3>
      <p className="hk-section-note">这些活动来自官方目录，但页面自己没有称它们为黑客松。</p>
      {[...groups.relatedCurrent, ...groups.relatedArchive].map(event => <EventCard key={event.id} event={event} focus={focus} csrf={csrf} />)}
    </div>}
  </section>;
}

function Header({ checkedAt }: { checkedAt?: string }) {
  return <PageHeader eyebrow="BNB CHAIN / SOLANA" title="黑客松监控" description="长期核对 BNB Chain / BSC 和 Solana 的官方黑客松。时间都写成北京时间（UTC+8）。投稿和获奖只在官方公开名单里出现；问卷和报名链接不是名单。" actions={checkedAt ? <Badge tone="info">最近核对 {checkedAt} 北京时间</Badge> : <Badge tone="warning">等待首次核对</Badge>} />;
}

const SOURCE_LABEL: Record<string, string> = {
  "binance-announcement": "币安公告",
  hackquest: "HackQuest",
  "luma-event": "Luma",
  "bnb-news": "BNB 官方文章",
  solana: "Solana 官网",
  colosseum: "Colosseum",
  external: "Superteam",
  magicblock: "MagicBlock",
};

function EventCard({ event, focus, csrf }: { event: HackathonEvent; focus: ListFocus | null; csrf: string }) {
  const winners = event.results.projects;
  const submissions = event.submission.projects;
  const listed = winners.length > 0 || submissions.length > 0 || (event.results.project_total ?? 0) > 0 || (event.submission.project_total ?? 0) > 0 || (event.side_tracks?.length ?? 0) > 0;
  const side = chainSide(event);
  const label = chainLabel(event);
  const badge = event.tracking_label || PHASE_LABEL[event.phase];
  return <Panel className={listed ? "hk-card hk-card-listed" : "hk-card hk-card-empty"} title={<>{label && <span className={`hk-chain hk-chain-${side}`}>{label}</span>}{event.title}</>} description={event.classification_reason} actions={<Badge tone={event.tracking_label === "已截稿" ? "warning" : event.tracking_label === "已公布结果" ? "success" : PHASE_TONE[event.phase]}>{badge}</Badge>}>
    <div className="hk-meta">
      {event.location && <span>{event.location}</span>}
      {event.prize && <span>{event.prize}</span>}
      {event.official_status && <span>官方状态：{event.official_status}</span>}
      {!event.listed && <span>目录状态：已不在最新目录</span>}
    </div>
    {event.documents && event.documents.length > 0 && <p className="hk-docs">{event.documents.map(item => <a key={item.url + item.role} href={item.url}>{item.label}</a>)}</p>}
    <PublicationTimes publication={event.publication} />
    {(event.website || event.twitter) && <p className="hk-event-links">
      {event.website && <a href={event.website}>赛事官网</a>}
      {event.twitter && <a href={event.twitter}>赛事官推</a>}
    </p>}
    {event.missing_note && <p className="hk-note">{event.missing_note}</p>}
    {(winners.length > 0 || (event.results.project_total ?? 0) > 0) && <ProjectList title="排名" ranked badge={event.publication?.winner.status_label} tone={event.publication?.winner.status === "published" ? "success" : "warning"} note={event.results.note} projects={winners} total={event.results.project_total ?? winners.length} eventId={event.id} eventTitle={event.title} list="results" focus={focus} csrf={csrf} />}
    {(submissions.length > 0 || (event.submission.project_total ?? 0) > 0) && <ProjectList title="名单" badge={event.publication?.submission.status_label} tone={event.publication?.submission.status === "published" ? "success" : event.publication?.submission.status === "error" ? "danger" : "warning"} note={event.submission.note} projects={submissions} total={event.submission.project_total ?? submissions.length} eventId={event.id} eventTitle={event.title} list="submission" focus={focus} csrf={csrf} />}
    {!listed && !event.side_tracks?.length && <p className="hk-empty-line">{event.submission.note || EMPTY_COPY.noSubmissions} {event.results.note || EMPTY_COPY.noResults}</p>}
    {event.side_tracks && event.side_tracks.length > 0 && <section className="hk-side">
      <h3>Superteam 赛道 <span className="hk-count">共 {event.side_tracks.length} 条，不是主办方总榜</span></h3>
      {event.side_tracks.map(track => <article key={track.url} className="hk-side-track">
        <h4><a href={track.url}>{track.name}</a> <span className="hk-count">{track.label}</span></h4>
        <p className="hk-note">{track.note}{track.published_at_display ? ` 公布时间 ${track.published_at_display}` : ""}{track.first_seen_display ? ` 首次看到 ${track.first_seen_display}` : ""}</p>
        {(track.winners.length > 0 || (track.winner_total ?? 0) > 0) && <ProjectList title="赛道获奖" ranked note="Superteam 赛道公布的名次。" projects={track.winners} total={track.winner_total ?? track.winners.length} eventId={event.id} eventTitle={event.title} list="side-winners" track={track.url} focus={focus} csrf={csrf} tone="success" />}
        {(track.works.length > 0 || (track.work_total ?? 0) > 0) && <ProjectList title="赛道作品" note="Superteam 赛道公开的作品。" projects={track.works} total={track.work_total ?? track.works.length} eventId={event.id} eventTitle={event.title} list="side-works" track={track.url} focus={focus} csrf={csrf} tone="warning" />}
        {!track.winners.length && !track.works.length && !(track.winner_total || track.work_total) && <p className="hk-empty-line">这条赛道还没有公开作品或获奖。</p>}
      </article>)}
    </section>}
    {event.submission.form_url && <p className="hk-note"><a href={event.submission.form_url}>官方提交或报名入口</a>。这不是公开名单。</p>}
    {event.summary && <p className="hk-summary">{event.summary}</p>}
    <details className="hk-schedule">
      <summary>日程{event.milestones.length ? ` · ${event.milestones.length} 个节点` : " · 来源未给出可换算的时刻"}</summary>
      {event.milestones.length ? <dl className="hk-milestones">{event.milestones.map(item => <div key={item.key}><dt>{item.label}</dt><dd>{item.display} <a href={item.source_url}>来源</a></dd></div>)}</dl> : <p className="hk-note">来源没有给出可以换算的开始、结束或其他节点。</p>}
    </details>
    {event.links.length > 0 && <p className="hk-links">{event.links.map(link => <a key={link.url} href={link.url}>{SOURCE_LABEL[link.label] || link.label}</a>)}</p>}
  </Panel>;
}

function ProjectList({ title, ranked = false, badge, tone, note, projects, total, eventId, eventTitle, list, track, focus, csrf }: { title: string; ranked?: boolean; badge?: string; tone: "success" | "warning" | "danger"; note: string; projects: HackathonProject[]; total: number; eventId: string; eventTitle: string; list: ProjectListKind; track?: string; focus: ListFocus | null; csrf: string }) {
  const active = focus?.eventId === eventId && focus.list === list && (focus.track || undefined) === track;
  const page = active ? focus.page : 0;
  const missingSite = projects.some(project => !project.website || !project.twitter);
  const pages = Math.max(1, Math.ceil(total / LIST_PAGE_SIZE));
  return <section className="hk-list">
    <h3>{title}{badge ? <Badge tone={tone}>{badge}</Badge> : null}<span className="hk-count">共 {total} 个</span></h3>
    <p className="hk-note">{note}{projects.length > 0 && missingSite ? " 来源没有写出的官网或官推不会补上。" : ""} {projects.length > 0 && total > projects.length ? (page ? `第 ${page} 页，每页 ${LIST_PAGE_SIZE} 个。` : `先显示 ${Math.min(LIST_PREVIEW, projects.length)} 个。`) : ""}</p>
    {projects.length > 0 && <ol className="hk-projects" start={page ? (page - 1) * LIST_PAGE_SIZE + 1 : 1}>{projects.map(project => {
      const handle = officialHandle(project.twitter);
      return <li key={`${project.role}-${project.name}-${project.place}`} className="hk-row">
      <span className="hk-rank">{project.place || (ranked ? "排名未公布" : "")}</span>
      <div>
        <strong>{project.name}</strong>
        {project.track && project.track !== project.place && <span className="hk-track">{project.track}</span>}
        {project.note && <span className="hk-track">{project.note}</span>}
        {project.info && <p className="hk-info">{project.info}</p>}
        <p className="hk-row-links">
          {project.website && <a href={project.website}>官网</a>}
          {handle && <a href={project.twitter}>@{handle} 官推</a>}
          {handle && <WatchButton handle={handle} project={project.name} eventTitle={eventTitle} eventId={eventId} csrf={csrf} />}
          {project.source_url && project.source_url !== project.website && <a href={project.source_url}>来源</a>}
        </p>
      </div>
    </li>;
    })}</ol>}
    {total > LIST_PREVIEW && <p className="hk-pager">
      {page > 1 && <a href={listHref(eventId, list, page - 1, track)}>上一页</a>}
      {page < pages && <a href={listHref(eventId, list, Math.max(page, 1) + (page ? 1 : 0), track)}>{page ? "下一页" : "查看更多"}</a>}
      <span>共 {pages} 页</span>
    </p>}
  </section>;
}

function listHref(eventId: string, list: ProjectListKind, page: number, track?: string) {
  const query = new URLSearchParams({ event: eventId, list, page: String(page) });
  if (track) query.set("track", track);
  return `/hackathons?${query.toString()}`;
}

function PublicationTimes({ publication }: { publication?: HackathonEvent["publication"] }) {
  const rows = [
    ["投稿公示开始", publication?.submission.published_at_display],
    ["投稿公示结束", ""],
    ["首次看到投稿名单", publication?.submission.first_seen_display],
    ["获奖公示开始", publication?.winner.published_at_display],
    ["获奖公示结束", ""],
    ["首次看到获奖名单", publication?.winner.first_seen_display],
  ].filter((row): row is [string, string] => Boolean(row[1]));
  if (!rows.length) return null;
  return <dl className="hk-window">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

function rankValue(place: string): number {
  const match = /(\d+)/.exec(place);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}
