import { AppShell } from "@ikun/ui";
import "@ikun/ui/styles.css";
import "../hackathons/hackathon.css";
import { requireAuthPage } from "../../lib/auth";
import { WorkspaceLink } from "../../components/auth/forms";
import { analyzePendingHackathonTweets } from "../../lib/hackathon-tweet-pass";
import { listTweetAnalyses, listTweets, listWatches, refreshActiveWatches } from "../../lib/hackathon-watches";
import { HackathonTweetBoard } from "./board";

export const dynamic = "force-dynamic";

export default async function HackathonTweetsPage() {
  const session = await requireAuthPage("/hackathon-tweets");
  await refreshActiveWatches();
  await analyzePendingHackathonTweets();
  const watches = listWatches();
  const tweets = listTweets();
  return <div className="hk-page"><AppShell pathname="/hackathon-tweets" LinkComponent={WorkspaceLink} footer={<p>只保存黑客松官推监控。不写入猎手发现或猎手项目监控。</p>}>
    <HackathonTweetBoard watches={watches} tweets={tweets} analyses={listTweetAnalyses()} csrf={session.csrf_token} />
  </AppShell></div>;
}
