import React from "react";
import { Badge, EmptyState, PageHeader, Panel } from "@ikun/ui";
import { beijingLabel, type HackathonTweet, type HackathonTweetAnalysis, type HackathonWatch } from "../../lib/hackathon-watch-model";
import { RemoveWatch } from "./remove-watch";

export function HackathonTweetBoard({ watches, tweets, analyses = {}, csrf = "", confirmId = "" }: { watches: HackathonWatch[]; tweets: HackathonTweet[]; analyses?: Record<string, HackathonTweetAnalysis>; csrf?: string; confirmId?: string }) {
  const active = watches.filter(watch => !watch.removed_at);
  return <div className="hk-board">
    <PageHeader eyebrow="HACKATHON" title="黑客松推文监控" description="只显示从黑客松名单里点过「监控」的官方账号。写明具体时间的推文会按北京时间进入主页时间线。删除后这条时间线也不再显示它，不影响猎手项目。" actions={<Badge tone="info">{active.length} 个监控中</Badge>} />
    <Panel title="监控中的官推">
      {active.length ? <ul className="hk-watch-list">{active.map(watch => <li key={watch.id}>
        <div><strong>{watch.project_name}</strong> <a href={`https://x.com/${watch.handle}`}>@{watch.handle}</a></div>
        <p className="hk-note">{watch.event_title || "未填写赛事"} · 开始于 {beijingLabel(watch.created_at)}</p>
        <RemoveWatch id={watch.id} csrf={csrf} initial={confirmId === watch.id ? "confirm" : "idle"} />
      </li>)}</ul> : <EmptyState title="还没有黑客松官推监控" description="在黑客松名单里，只有来源给出了官推的项目才会出现监控按钮。" />}
    </Panel>
    <Panel title="推文">
      {tweets.length ? <ol className="hk-tweets">{tweets.map(tweet => <li key={tweet.id}>
        <p><strong>{tweet.project_name}</strong> @{tweet.handle}{tweet.removed ? " · 已停止监控" : ""}</p>
        <p>{tweet.text}</p>
        <p className="hk-note"><a href={tweet.url}>原推</a> · 推文时间 {beijingLabel(tweet.occurred_at)}</p>
        {analyses[tweet.id] ? <p className="hk-note">AI 分析：{analyses[tweet.id]?.analysis}{analyses[tweet.id]?.starts_at ? ` · 时间点 ${beijingLabel(analyses[tweet.id].starts_at!)}` : ""}</p> : null}
      </li>)}</ol> : <EmptyState title="还没有读到新推文" description="监控开始之后的公开推文才会出现。读不到时这里保持空白，不会编造推文。" />}
    </Panel>
  </div>;
}
