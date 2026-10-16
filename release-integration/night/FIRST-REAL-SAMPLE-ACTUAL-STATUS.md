# 首次真实样本当前状态

{
  "state": "BLOCKED_ADD_RECEIPT_NEW_ID_UNPROVEN",
  "at": "2026-10-16T14:55:56.094788+00:00",
  "setup_profile_reads": 1,
  "setup_watch_reads": 1,
  "watch_add_attempts": 1,
  "observation_reads": 0,
  "new_wss_connections": 0,
  "native_stops": 0,
  "existing_watch_mutations": 0,
  "new_watch_disposition": "preserve_no_retry_no_delete",
  "receipt_sha256": "66a4019adf8d38c6e84138934d6e79e693c7613fa310b2bef0eb59fde642728c",
  "requires": "explicitly reviewed readback/proof adaptation; do not fabricate id or twGroupId"
}

原新增回执 data 仅含 cost/groupId/message/success/username，缺少 Watch id 和 twGroupId。冻结 minter 无法构建真实 proof，尚未创建 Projects/Tracking 业务记录，未停 Worker、未 mint、未开 WSS；不可通知用户发推。新增测试 Watch 保留，不重试、不清理。原始回执位于私有 actual-setup 目录。

## 经明确授权的一次额外只读回查

实际回查找到唯一测试条目：真实 id 存在，twGroupId 与 add 原回执 groupId 一致；newTweetBol/newTweetQuoteBol=true，其余 Bol=false。原始回执和新增回查分开保留，没有改写 add 原回执。实际本轮计数为 profile1 + Watch before1 + add1 + 额外 reconcile Watch1；WSS0，停服0。原 NewProof setup_watch_read_attempts=1 与实际准备/补证两次 Watch 读取不符，原704观察段仍会自行再读一次；不得把额外回查隐去或当作已发生的观察段读取。需要冻结样本 owner 最小修订证明允许并绑定本次额外回查（含真实时间/hash），原 strict-active/flags/额度和最多一次新增约束保持，然后重新取得短时实时输入。本轮尚未 READY，请勿安排发推。

## v2 本地收口，真实执行停止

Tracking 原 worktree 提交 b728f1e990896133359e89b5c5a9d1bad793bfce：保留 v1 严格一次，显式 proof-v2 严格两次，绑定未改写 add 和独立 readback，新增11项回归；原样本定向文件95项通过（初跑唯一回环 bind 受沙盒限制，授权重跑95通过）。integration 胶水10项通过，版本2仅允许准确 b728f1e 源，未收件到 staged、未启动。

真实创建 intent=1792162536.56938，上海时间2026-10-16 22:55:36.569，严格300秒截至23:00:36.569。实际执行已停止，不取得新profile、不创建Projects/Tracking记录、不停服、不mint、不发WSS。v2不放宽创建新鲜性。

下一项仅离线准备v3候选：把该次已证明自有Watch的创建时间作为不可变历史证据，fresh profile/唯一完整回查/明确授权仍≤300秒。此变化必须显式复审放行；当前不具备真实运行许可。
