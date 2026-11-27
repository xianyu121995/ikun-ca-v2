import { readFileSync } from "node:fs";

export type Phase = "live" | "upcoming" | "ended" | "unknown";
export type Classification = "hackathon" | "related";

export interface HackathonProject {
  name: string;
  role: "submitted" | "winner" | "selected" | "shortlisted";
  place: string;
  track: string;
  url: string;
  source_url: string;
  note: string;
}

export interface HackathonMilestone {
  key: string;
  label: string;
  display: string;
  precision: string;
  source_url: string;
  start_utc: string | null;
  end_utc: string | null;
}

export interface HackathonEvent {
  id: string;
  title: string;
  classification: Classification;
  classification_reason: string;
  summary: string;
  location: string;
  prize: string;
  official_status: string | null;
  phase: Phase;
  phase_basis: string;
  start_utc: string | null;
  end_utc: string | null;
  listed: boolean;
  missing_note: string;
  submission: { state: "public" | "private_form" | "not_published" | "unknown"; note: string; form_url: string | null; projects: HackathonProject[] };
  results: { state: "published" | "not_published"; note: string; projects: HackathonProject[] };
  milestones: HackathonMilestone[];
  links: { label: string; url: string }[];
}

export interface HackathonSnapshot {
  schema: "hackathon-snapshot-v1";
  generated_at: string;
  generated_at_beijing: string;
  timezone: "Asia/Shanghai";
  standing: true;
  sources: { id: string; url: string; ok: boolean; checked_at: string; error: string; note: string }[];
  events: HackathonEvent[];
}

export type SnapshotLoad =
  | { ok: true; snapshot: HackathonSnapshot }
  | { ok: false; reason: "unconfigured" | "missing" | "invalid" };

const PHASES = new Set(["live", "upcoming", "ended", "unknown"]);

export function parseSnapshot(value: unknown): HackathonSnapshot | null {
  if (!value || typeof value !== "object") return null;
  const snapshot = value as HackathonSnapshot;
  if (snapshot.schema !== "hackathon-snapshot-v1" || snapshot.timezone !== "Asia/Shanghai" || snapshot.standing !== true) return null;
  if (!Array.isArray(snapshot.events) || !Array.isArray(snapshot.sources)) return null;
  for (const event of snapshot.events) {
    if (!event || typeof event.title !== "string" || !event.title.trim()) return null;
    if (event.classification !== "hackathon" && event.classification !== "related") return null;
    if (!PHASES.has(event.phase)) return null;
    if (!event.submission || !event.results || !Array.isArray(event.milestones) || !Array.isArray(event.links)) return null;
    for (const project of [...event.submission.projects, ...event.results.projects]) {
      if (!project?.name?.trim() || typeof project.source_url !== "string" || !project.source_url.startsWith("https://")) return null;
    }
    for (const milestone of event.milestones) {
      if (!milestone?.display || !milestone.source_url?.startsWith("https://")) return null;
    }
  }
  return snapshot;
}

export function readHackathonSnapshot(path: string | undefined): SnapshotLoad {
  if (!path) return { ok: false, reason: "unconfigured" };
  try {
    const parsed = parseSnapshot(JSON.parse(readFileSync(path, "utf8")));
    return parsed ? { ok: true, snapshot: parsed } : { ok: false, reason: "invalid" };
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    return { ok: false, reason: code === "ENOENT" ? "missing" : "invalid" };
  }
}

export function phaseAt(event: Pick<HackathonEvent, "official_status" | "start_utc" | "end_utc" | "phase">, now: Date): Phase {
  const status = (event.official_status || "").trim().toLowerCase();
  if (["ended", "已结束", "complete", "completed", "closed"].includes(status)) return "ended";
  const start = event.start_utc ? Date.parse(event.start_utc) : NaN;
  const end = event.end_utc ? Date.parse(event.end_utc) : NaN;
  const time = now.getTime();
  if (Number.isFinite(start) && time < start) return "upcoming";
  if (Number.isFinite(end) && time >= end) return "ended";
  if (Number.isFinite(start) && Number.isFinite(end) && time >= start && time < end) return "live";
  return event.phase === "ended" ? "unknown" : event.phase;
}

export interface HackathonGroups {
  current: HackathonEvent[];
  archive: HackathonEvent[];
  relatedCurrent: HackathonEvent[];
  relatedArchive: HackathonEvent[];
}

export function groupEvents(events: HackathonEvent[], now: Date): HackathonGroups {
  const stamped = events.map(event => ({ ...event, phase: phaseAt(event, now) }));
  const hackathons = stamped.filter(event => event.classification === "hackathon");
  const related = stamped.filter(event => event.classification === "related");
  const byStart = (left: HackathonEvent, right: HackathonEvent) => (left.start_utc || "9999").localeCompare(right.start_utc || "9999");
  const byEnd = (left: HackathonEvent, right: HackathonEvent) => (right.end_utc || "").localeCompare(left.end_utc || "");
  return {
    current: hackathons.filter(event => event.phase !== "ended").sort(byStart),
    archive: hackathons.filter(event => event.phase === "ended").sort(byEnd),
    relatedCurrent: related.filter(event => event.phase !== "ended").sort(byStart),
    relatedArchive: related.filter(event => event.phase === "ended").sort(byEnd),
  };
}

export const EMPTY_COPY = {
  unconfigured: "还没有配置监控快照。这是长期运行的核对服务写出的文件，页面不会编造活动。",
  missing: "快照还不存在。服务第一次核对到官方来源后，进行中的活动和已结束归档都会出现在这里。",
  invalid: "快照无法读取。页面不会用残缺内容冒充官方日程或名单。",
  noCurrent: "当前没有进行中或即将开始的官方黑客松。新的官方活动公布后会出现在这里。",
  noArchive: "归档是空的。已结束的活动会留在这里，不会在结束后被删掉。",
  noSubmissions: "已核对的官方来源没有公布投稿项目。",
  privateForm: "官方只提供了提交或报名入口，没有公开的项目列表。入口不是排行榜。",
  noResults: "官方还没有公布入选或获奖项目。",
} as const;
