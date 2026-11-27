import React from "react";
import { Alert, Badge, EmptyState, PageHeader, Panel } from "@ikun/ui";
import { EMPTY_COPY, groupEvents, type HackathonEvent, type HackathonProject, type Phase, type SnapshotLoad } from "../../lib/hackathon-snapshot";

const PHASE_LABEL: Record<Phase, string> = { live: "进行中", upcoming: "即将开始", ended: "已结束", unknown: "时间未明" };
const PHASE_TONE: Record<Phase, "success" | "info" | "neutral" | "warning"> = { live: "success", upcoming: "info", ended: "neutral", unknown: "warning" };

export function HackathonBoard({ load, now }: { load: SnapshotLoad; now: string }) {
  if (!load.ok) {
    return <div className="hk-board">
      <Header />
      <EmptyState title="监控还没有可展示的快照" description={EMPTY_COPY[load.reason]} />
    </div>;
  }
  const failed = load.snapshot.sources.filter(source => !source.ok);
  return <div className="hk-board">
    <Header checkedAt={load.snapshot.generated_at_beijing} />
    <Alert tone="warning" title="这里看不到全部投稿">{EMPTY_COPY.notEverything}</Alert>
    {load.snapshot.changes && load.snapshot.changes.length > 0 && <section className="hk-section" aria-labelledby="hk-changes">
      <h2 id="hk-changes">最近变化</h2>
      <ul className="hk-changes">{load.snapshot.changes.slice(-12).reverse().map(change => <li key={change.id}><strong>{change.label}</strong> {change.event}{change.at_beijing ? ` · ${change.at_beijing} 北京时间` : ""}</li>)}</ul>
    </section>}
    {failed.length > 0 && <Alert tone="warning" title="有来源这次没有核对成功">{failed.map(source => <p key={source.id}>{source.id}：{source.error || "失败"}。上次成功的内容会保留。</p>)}</Alert>}
    <Ecosystem id="bnb" title="BNB Chain / BSC" events={load.snapshot.events.filter(event => event.ecosystem === "bnb" || event.ecosystem === "both")} now={now} />
    <Ecosystem id="solana" title="Solana" events={load.snapshot.events.filter(event => event.ecosystem === "solana" || event.ecosystem === "both")} now={now} />
  </div>;
}

function Ecosystem({ id, title, events, now }: { id: string; title: string; events: HackathonEvent[]; now: string }) {
  const groups = groupEvents(events, new Date(now));
  return <section className="hk-ecosystem" aria-labelledby={`hk-${id}`}>
    <h2 id={`hk-${id}`}>{title}</h2>
    <div className="hk-section" aria-labelledby={`hk-${id}-current`}>
      <h3 id={`hk-${id}-current`}>进行中与即将开始</h3>
      {groups.current.length ? groups.current.map(event => <EventCard key={event.id} event={event} />) : <EmptyState title="没有进行中的黑客松" description={EMPTY_COPY.noCurrent} />}
    </div>
    <div className="hk-section" aria-labelledby={`hk-${id}-archive`}>
      <h3 id={`hk-${id}-archive`}>已结束（归档）</h3>
      <p className="hk-section-note">归档会一直保留。监控不会在某一届结束后停掉，也不会把结束当成删除。</p>
      {groups.archive.length ? groups.archive.map(event => <EventCard key={event.id} event={event} />) : <EmptyState title="归档还是空的" description={EMPTY_COPY.noArchive} />}
    </div>
    {(groups.relatedCurrent.length > 0 || groups.relatedArchive.length > 0) && <div className="hk-section" aria-labelledby={`hk-${id}-related`}>
      <h3 id={`hk-${id}-related`}>相关官方活动</h3>
      <p className="hk-section-note">这些活动来自官方目录，但页面自己没有称它们为黑客松。</p>
      {[...groups.relatedCurrent, ...groups.relatedArchive].map(event => <EventCard key={event.id} event={event} />)}
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
};

function EventCard({ event }: { event: HackathonEvent }) {
  const winners = event.results.projects;
  const submissions = event.submission.projects;
  const listed = winners.length > 0 || submissions.length > 0;
  return <Panel className={listed ? "hk-card hk-card-listed" : "hk-card hk-card-empty"} title={event.title} description={event.classification_reason} actions={<Badge tone={PHASE_TONE[event.phase]}>{PHASE_LABEL[event.phase]}</Badge>}>
    <div className="hk-meta">
      {event.location && <span>{event.location}</span>}
      {event.prize && <span>{event.prize}</span>}
      {event.official_status && <span>官方状态：{event.official_status}</span>}
      {!event.listed && <span>目录状态：已不在最新目录</span>}
    </div>
    {(event.website || event.twitter) && <p className="hk-event-links">
      {event.website && <a href={event.website}>赛事官网</a>}
      {event.twitter && <a href={event.twitter}>赛事官推</a>}
    </p>}
    {event.missing_note && <p className="hk-note">{event.missing_note}</p>}
    {winners.length > 0 && <ProjectList title="排名" ranked badge={event.publication?.winner.status_label} tone={event.publication?.winner.status === "published" ? "success" : "warning"} note={event.results.note} projects={winners} />}
    {submissions.length > 0 && <ProjectList title="名单" badge={event.publication?.submission.status_label} tone={event.publication?.submission.status === "published" ? "success" : event.publication?.submission.status === "error" ? "danger" : "warning"} note={event.submission.note} projects={submissions} />}
    {!listed && <p className="hk-empty-line">{event.submission.note || EMPTY_COPY.noSubmissions} {event.results.note || EMPTY_COPY.noResults}</p>}
    {event.submission.form_url && <p className="hk-note"><a href={event.submission.form_url}>官方提交或报名入口</a>。这不是公开名单。</p>}
    {event.summary && <p className="hk-summary">{event.summary}</p>}
    <details className="hk-schedule">
      <summary>日程{event.milestones.length ? ` · ${event.milestones.length} 个节点` : " · 来源未给出可换算的时刻"}</summary>
      {event.milestones.length ? <dl className="hk-milestones">{event.milestones.map(item => <div key={item.key}><dt>{item.label}</dt><dd>{item.display} <a href={item.source_url}>来源</a></dd></div>)}</dl> : <p className="hk-note">来源没有给出可以换算的开始、结束或其他节点。</p>}
    </details>
    {event.links.length > 0 && <p className="hk-links">{event.links.map(link => <a key={link.url} href={link.url}>{SOURCE_LABEL[link.label] || link.label}</a>)}</p>}
  </Panel>;
}

function ProjectList({ title, ranked = false, badge, tone, note, projects }: { title: string; ranked?: boolean; badge?: string; tone: "success" | "warning" | "danger"; note: string; projects: HackathonProject[] }) {
  const ordered = ranked ? [...projects].sort((left, right) => rankValue(left.place) - rankValue(right.place)) : projects;
  const missingSite = ordered.some(project => !project.website || !project.twitter);
  return <section className="hk-list">
    <h3>{title}{badge ? <Badge tone={tone}>{badge}</Badge> : null}<span className="hk-count">共 {projects.length} 个</span></h3>
    <p className="hk-note">{note}{missingSite ? " 来源没有写出的官网或官推不会补上。" : ""}</p>
    <ol className="hk-projects">{ordered.map(project => <li key={`${project.role}-${project.name}-${project.place}`} className="hk-row">
      <span className="hk-rank">{project.place || (ranked ? "排名未公布" : "")}</span>
      <div>
        <strong>{project.name}</strong>
        {project.track && project.track !== project.place && <span className="hk-track">{project.track}</span>}
        {project.note && <span className="hk-track">{project.note}</span>}
        {project.info && <p className="hk-info">{project.info}</p>}
        <p className="hk-row-links">
          {project.website && <a href={project.website}>官网</a>}
          {project.twitter && <a href={project.twitter}>官推</a>}
          {project.source_url && project.source_url !== project.website && <a href={project.source_url}>来源</a>}
        </p>
      </div>
    </li>)}</ol>
  </section>;
}

function rankValue(place: string): number {
  const match = /(\d+)/.exec(place);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}
