import { AppShell } from "@ikun/ui";
import "@ikun/ui/styles.css";
import "./hackathon.css";
import { requireAuthPage } from "../../lib/auth";
import { readHackathonSnapshot } from "../../lib/hackathon-snapshot";
import { WorkspaceLink } from "../../components/auth/forms";
import { HackathonBoard } from "./board";

export const dynamic = "force-dynamic";

export default async function HackathonsPage() {
  await requireAuthPage("/hackathons");
  const load = readHackathonSnapshot(process.env.IKUN_HACKATHON_SNAPSHOT);
  return <div className="hk-page"><AppShell pathname="/hackathons" LinkComponent={WorkspaceLink} footer={<p>长期核对 · 只读官方来源 · 已结束的活动留在归档</p>}>
    <HackathonBoard load={load} now={new Date().toISOString()} />
  </AppShell></div>;
}
