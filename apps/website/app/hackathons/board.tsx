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
  const groups = groupEvents(load.snapshot.events, new Date(now));
  const failed = load.snapshot.sources.filter(source => !source.ok);
  return <div className="hk-board">
    <Header checkedAt={load.snapshot.generated_at_beijing} />
    {failed.length > 0 && <Alert tone="warning" title="有来源这次没有核对成功">{failed.map(source => <p key={source.id}>{source.id}：{source.error || "失败"}。上次成功的内容会保留。</p>)}</Alert>}
    <section className="hk-section" aria-labelledby="hk-current">
      <h2 id="hk-current">进行中与即将开始</h2>
      {groups.current.length ? groups.current.map(event => <EventCard key={event.id} event={event} />) : <EmptyState title="没有进行中的黑客松" description={EMPTY_COPY.noCurrent} />}
    </section>
    <section className="hk-section" aria-labelledby="hk-archive">
      <h2 id="hk-archive">已结束（归档）</h2>
      <p className="hk-section-note">归档会一直保留。监控不会在某一次活动结束后停掉，也不会把结束当成删除。</p>
      {groups.archive.length ? groups.archive.map(event => <EventCard key={event.id} event={event} />) : <EmptyState title="归档还是空的" description={EMPTY_COPY.noArchive} />}
    </section>
    {(groups.relatedCurrent.length > 0 || groups.relatedArchive.length > 0) && <section className="hk-section" aria-labelledby="hk-related">
      <h2 id="hk-related">相关官方活动</h2>
      <p className="hk-section-note">这些活动来自官方黑客松目录或公告，但页面自己没有称它们为黑客松。它们和黑客松分开列出。</p>
      {[...groups.relatedCurrent, ...groups.relatedArchive].map(event => <EventCard key={event.id} event={event} />)}
    </section>}
  </div>;
}

function Header({ checkedAt }: { checkedAt?: string }) {
  return <PageHeader eyebrow="BNB CHAIN / BSC" title="黑客松监控" description="长期核对 BNB Chain 与 BSC 的官方黑客松，以及官方目录里明确分开的同类活动。时间都写成北京时间（UTC+8）。只展示能打开来源链接的日程、公开投稿和官方公布的入选或获奖项目。" actions={checkedAt ? <Badge tone="info">最近核对 {checkedAt} 北京时间</Badge> : <Badge tone="warning">等待首次核对</Badge>} />;
}

function EventCard({ event }: { event: HackathonEvent }) {
  return <Panel className="hk-card" title={event.title} description={event.classification_reason} actions={<Badge tone={PHASE_TONE[event.phase]}>{PHASE_LABEL[event.phase]}</Badge>}>
    <div className="hk-meta">
      {event.location && <span>{event.location}</span>}
      {event.prize && <span>{event.prize}</span>}
      {event.official_status && <span>官方状态：{event.official_status}</span>}
      {!event.listed && <span>目录状态：已不在最新目录</span>}
    </div>
    {event.missing_note && <p className="hk-note">{event.missing_note}</p>}
    {event.summary && <p className="hk-summary">{event.summary}</p>}
    <h3>日程</h3>
    {event.milestones.length ? <dl className="hk-milestones">{event.milestones.map(item => <div key={item.key}><dt>{item.label}</dt><dd>{item.display} <a href={item.source_url}>来源</a></dd></div>)}</dl> : <EmptyState title="没有已核实的时刻" description="来源没有给出可以换算的开始、结束或其他节点。" />}
    <h3>投稿项目</h3>
    <ProjectBlock state={event.submission.state} note={event.submission.note} projects={event.submission.projects} empty={event.submission.state === "private_form" ? EMPTY_COPY.privateForm : EMPTY_COPY.noSubmissions} />
    {event.submission.form_url && <p className="hk-note"><a href={event.submission.form_url}>官方提交或报名入口</a>。这不是公开名单。</p>}
    <h3>入选 / 获奖</h3>
    <ProjectBlock state={event.results.state} note={event.results.note} projects={event.results.projects} empty={EMPTY_COPY.noResults} />
    {event.links.length > 0 && <p className="hk-links">{event.links.map(link => <a key={link.url} href={link.url}>{link.label}</a>)}</p>}
  </Panel>;
}

function ProjectBlock({ projects, note, empty }: { state: string; note: string; projects: HackathonProject[]; empty: string }) {
  if (!projects.length) return <EmptyState title="没有可展示的项目" description={note || empty} />;
  return <div>
    <p className="hk-note">{note}</p>
    <ul className="hk-projects">{projects.map(project => <li key={`${project.role}-${project.name}`}>
      <strong>{project.name}</strong>
      {project.place && <span> · {project.place}</span>}
      {project.track && project.track !== project.place && <span> · {project.track}</span>}
      {project.url && <> · <a href={project.url}>项目链接</a></>}
      {" "}· <a href={project.source_url}>来源</a>
    </li>)}</ul>
  </div>;
}
