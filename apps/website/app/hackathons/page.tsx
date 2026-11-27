import { AppShell } from "@ikun/ui";
import "@ikun/ui/styles.css";
import "./hackathon.css";
import { requireAuthPage } from "../../lib/auth";
import { paintSnapshot, parseListFocus, readHackathonSnapshot } from "../../lib/hackathon-snapshot";
import { listAnalyses, listNotes } from "../../lib/hackathon-watches";
import { WorkspaceLink } from "../../components/auth/forms";
import { HackathonBoard } from "./board";

export const dynamic = "force-dynamic";

export default async function HackathonsPage({ searchParams }: { searchParams?: Promise<Record<string, string | string[] | undefined>> }) {
  const session = await requireAuthPage("/hackathons");
  const now = new Date().toISOString();
  const query = searchParams ? await searchParams : {};
  const focus = parseListFocus(query);
  const loaded = readHackathonSnapshot(process.env.IKUN_HACKATHON_SNAPSHOT);
  const load = loaded.ok ? { ok: true as const, snapshot: paintSnapshot(loaded.snapshot, new Date(now), focus) } : loaded;
  const stored = storedHackathonRecords();
  return <div className="hk-page"><AppShell pathname="/hackathons" LinkComponent={WorkspaceLink} footer={<p>长期核对 · 只读官方来源 · 已结束的活动留在归档</p>}>
    <HackathonBoard load={load} now={now} focus={focus} csrf={session.csrf_token} notes={stored.notes} analyses={stored.analyses} />
  </AppShell></div>;
}

function storedHackathonRecords() {
  try { return { notes: listNotes(), analyses: listAnalyses() }; }
  catch { return { notes: {}, analyses: {} }; }
}
