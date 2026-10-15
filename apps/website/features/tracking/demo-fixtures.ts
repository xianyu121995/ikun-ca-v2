import type { ActivityDTO, ProjectChoice, SubscriptionDTO } from "./types";
// Fixed, fictitious fixture identifiers; never generated or persisted as business IDs.
export const projectIds = [
  "prj_10000000-0000-4000-8000-000000000001", "prj_10000000-0000-4000-8000-000000000002",
  "prj_10000000-0000-4000-8000-000000000003", "prj_10000000-0000-4000-8000-000000000004",
  "prj_10000000-0000-4000-8000-000000000005", "prj_10000000-0000-4000-8000-000000000006",
  "prj_10000000-0000-4000-8000-000000000007", "prj_10000000-0000-4000-8000-000000000008",
  "prj_10000000-0000-4000-8000-000000000009",
] as const;
export const subscriptionIds = [
  "sub_20000000-0000-4000-8000-000000000001", "sub_20000000-0000-4000-8000-000000000002",
  "sub_20000000-0000-4000-8000-000000000003", "sub_20000000-0000-4000-8000-000000000004",
  "sub_20000000-0000-4000-8000-000000000005", "sub_20000000-0000-4000-8000-000000000006",
  "sub_20000000-0000-4000-8000-000000000007", "sub_20000000-0000-4000-8000-000000000008",
  "sub_20000000-0000-4000-8000-000000000009",
] as const;
export const fixtureCommandId = "cmd_30000000-0000-4000-8000-000000000001";
export const fixtureTime = "2026-10-15T00:00:00.000Z";
export function demoSubscriptions(): SubscriptionDTO[] {
  const states: [SubscriptionDTO["desired_state"], SubscriptionDTO["observed_state"], SubscriptionDTO["operation_state"], SubscriptionDTO["connection"]][] = [
    ["running", "running", "succeeded", "connected"], ["running", "stopped", "accepted", "connected"],
    ["running", "unknown", "unknown", "connected"], ["stopped", "stopped", "succeeded", "disconnected"],
    ["running", "stopped", "failed", "disconnected"], ["running", "unknown", "running", "connecting"],
    ["removed", "absent", "succeeded", "unconfigured"],
  ];
  const rows: SubscriptionDTO[] = ["Meridian Protocol", "Axiom Network", "Orbit Layer", "Lattice Labs", "Vela Finance", "Relay Protocol", "Prism Worlds"].map((name, i) => ({
    subscription_id: subscriptionIds[i], project_id: projectIds[i], name, x_handle: ["demo_meridian", "demo_axiom", "demo_orbit", "demo_lattice", "demo_vela", "demo_relay", "demo_prism"][i], x_user_id: null,
    notes: "虚构演示项目；与主页成员状态独立。", revision: 3,
    desired_state: states[i][0], observed_state: states[i][1], operation_state: states[i][2], connection: states[i][3],
    last_tweet_at: i === 5 ? null : `2026-10-14T23:${String(58 - i * 7).padStart(2, "0")}:00.000Z`, created_at: "2026-10-12T00:00:00.000Z", updated_at: fixtureTime,
  }));
  return [...rows, { ...rows[0], subscription_id: subscriptionIds[8], project_id: projectIds[8], name: "Beacon Labs", x_handle: "demo_beacon", desired_state: "stopped", observed_state: "absent", operation_state: "succeeded", connection: "unconfigured", last_tweet_at: null }];
}
export const demoProject: ProjectChoice = { project_id: projectIds[7], name: "Nimbus AI", x_handle: "demo_nimbus" };
export function demoActivities(): ActivityDTO[] {
  return [
    { activity_id: "fixture-activity-1", subscription_id: subscriptionIds[0], project_id: projectIds[0], project_name: "Meridian Protocol", tweet_id: "1001", x_handle: "demo_meridian", text: "The next chapter starts here.\nMeridian testnet v2 is opening to builders. A faster path from idea to onchain. ✦\n\n虚构示例内容，用于界面评审。", url: "https://x.com/demo_meridian/status/1001", occurred_at: "2026-10-14T23:58:00.000Z", received_at: "2026-10-14T23:58:01.000Z", source: "wss", generation: 1 },
    { activity_id: "fixture-activity-2", subscription_id: subscriptionIds[1], project_id: projectIds[1], project_name: "Axiom Network", tweet_id: "1002", x_handle: "demo_axiom", text: "Building the invisible layer.\nNew tooling, better observability, and one unified dashboard.\n\n本条未提供发生时间，只展示接收时间。", url: "https://x.com/demo_axiom/status/1002", occurred_at: null, received_at: "2026-10-14T23:50:00.000Z", source: "rest", generation: 2 },
    { activity_id: "fixture-activity-3", subscription_id: subscriptionIds[2], project_id: projectIds[2], project_name: "Orbit Layer", tweet_id: "1005", x_handle: "demo_orbit", text: "Devnet is taking its next step.\nThe new builder guide covers deployment, testing, and the first community experiments.\n\n虚构示例：开发网更新与社区建设进展。", url: "https://x.com/demo_orbit/status/1005", occurred_at: "2026-10-14T23:44:00.000Z", received_at: "2026-10-14T23:44:01.000Z", source: "wss", generation: 1 },
    { activity_id: "fixture-activity-4", subscription_id: subscriptionIds[3], project_id: projectIds[3], project_name: "Lattice Labs", tweet_id: "1006", x_handle: "demo_lattice", text: "Small improvements, better everyday tools.\nThis week we are sharing our research notes and an updated product walkthrough.\n\n虚构示例：项目停止监控后，已加载的历史推文仍可查看。", url: "https://x.com/demo_lattice/status/1006", occurred_at: "2026-10-14T23:37:00.000Z", received_at: "2026-10-14T23:37:01.000Z", source: "wss", generation: 1 },
    { activity_id: "fixture-activity-5", subscription_id: subscriptionIds[4], project_id: projectIds[4], project_name: "Vela Finance", tweet_id: "1007", x_handle: "demo_vela", text: "Our next community call is all about transparency.\nA closer look at the roadmap, design decisions, and what we are building together.\n\n虚构示例内容，不代表真实项目公告。", url: "https://x.com/demo_vela/status/1007", occurred_at: "2026-10-14T23:30:00.000Z", received_at: "2026-10-14T23:30:01.000Z", source: "rest", generation: 1 },
    { activity_id: "fixture-activity-6", subscription_id: subscriptionIds[0], project_id: projectIds[0], project_name: "Meridian Protocol", tweet_id: "1008", x_handle: "demo_meridian", text: "The builder handbook has a new chapter.\nExplore the architecture and follow the first deployment walkthrough.\n\n虚构示例：同一项目的历史推文。", url: "https://x.com/demo_meridian/status/1008", occurred_at: "2026-10-14T14:10:00.000Z", received_at: "2026-10-14T14:10:01.000Z", source: "wss", generation: 1 },
    { activity_id: "fixture-activity-7", subscription_id: subscriptionIds[1], project_id: projectIds[1], project_name: "Axiom Network", tweet_id: "1009", x_handle: "demo_axiom", text: "A new workspace for builders.\nOur community is testing an updated dashboard and sharing early feedback.\n\n虚构示例：社区产品体验进展。", url: "https://x.com/demo_axiom/status/1009", occurred_at: "2026-10-14T13:25:00.000Z", received_at: "2026-10-14T13:25:01.000Z", source: "wss", generation: 1 },
    { activity_id: "fixture-activity-8", subscription_id: subscriptionIds[2], project_id: projectIds[2], project_name: "Orbit Layer", tweet_id: "1010", x_handle: "demo_orbit", text: "Research notes: connecting applications with a simpler developer experience.\n\n虚构示例：研究笔记历史记录。", url: "https://x.com/demo_orbit/status/1010", occurred_at: "2026-10-14T12:40:00.000Z", received_at: "2026-10-14T12:40:01.000Z", source: "rest", generation: 1 },
  ];
}
export function demoIncomingActivities(): ActivityDTO[] {
  return [
    { ...demoActivities()[0], activity_id: "fixture-incoming-1", tweet_id: "1003", url: "https://x.com/demo_meridian/status/1003", text: "A fresh update from our builders.\nNew milestones, new possibilities. ✦\n\n手动插入的虚构新推文，用于展示动态进入页面。", occurred_at: "2026-10-15T00:01:00.000Z", received_at: "2026-10-15T00:01:01.000Z" },
    { ...demoActivities()[0], activity_id: "fixture-incoming-2", tweet_id: "1004", url: "https://x.com/demo_meridian/status/1004", text: "Community update is here.\n\n第二条预置示例，展示暂停期间的新消息暂存效果。", occurred_at: "2026-10-15T00:02:00.000Z", received_at: "2026-10-15T00:02:01.000Z" },
  ];
}
