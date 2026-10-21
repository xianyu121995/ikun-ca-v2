# Tracking 浏览器语音增量

依据总管 `d0af2804ed1ad70d3dd66e930582831bbd6b5e96:docs/progress/VOICE-RELEASE.md` 的 RELEASED 放行；本机音色裁定 `8fe35943d026c3d030c2dd42b2f889abe27f2422`。B3 冻结源码 `c4de379a67bd9b154bab87ce81d4645b53102ea0`，交付 `f3bc19503ae33e000bdd33c140baa1fe77c9109a`。原 UI 基线 `486294ac3255b08fdb13a307ee15f96c571020d9` 保留，原组件与页面未修改。

2026-10-20 用户更新：播报内容改为 Projects 的当前项目名称＋S/A/B 等级，不再依赖追踪备注。

2026-10-22 用户更新：网站改用 `consumePublished`，以 `/tracking/latest?profile=published-v1` 的 S/A/B 列表为准，REST 和 unknown 均可播。首个成功列表只建立基线；之后新增 ID 且服务器判断发布时间在十分钟内才播。SSE 仅触发立即读列表，另有十五秒轮询。浏览器独占锁与共享 ID 记录保证同一浏览器不重复发声，队列期限从每页实际到达的 `performance.now()` 起算三十秒。原 `consume` 保留兼容旧接线与测试，网站不再用它接收 SSE 候选。下面旧接线说明仅适用于兼容入口。

## 接线契约（集成窗口持有真实请求）

1. 浏览器页面创建一个 `TrackingVoiceController({speech: createWebSpeechPort(), storage: browserVoiceStorage(), resolveMetadata})`，渲染 `VoiceControls`。`storage` 不可用时省略该选项，控件诚实提示设置仅本页有效。模块导入/构造/恢复偏好均不会发声。
2. B1 验证成功后 `setSession({user_id,epoch,role})`；epoch 是当前登录会话的非秘密、不透明代号，不能用用户名代替 user_id，不传密码/会话 token。失效、退出、禁用、改密撤销立即 `setSession(null)`，会话变化必须换 epoch；角色仅接受 user/superadmin，两者均能管理自己的浏览器偏好。
3. 复用现有 B3 EventSource，open 时 `setStreamConnected(true, identity)`，error/close/撤销时立即传 false。只在现有 `tracking.feed.activity.created.v1` 回调调用 `consume({type:event.type,event_id:event.lastEventId,delivery:'live',data:parsedEnvelope.data}, identity)`；不要传完整 MessageEvent 或 raw/text。其他入口显式 delivery=history/replay/rest 会被拒绝。先校验原有 SSE envelope，初始帧/重连重放仍必须正确保留 replay 标记，不把 REST/分页转成新事件。
4. `resolveMetadata(candidate,{user_id,epoch,role,signal})` 返回以下最小投影或 null。适配器用已有 B1 保护的单订阅 GET 取得 revision、project_id，再用已有 Projects GET 取得对应当前项目名称、评级与 revision。必须核对 HTTP 成功和标准成功 envelope、实际 ID、正 revision，并透传 signal；建议单次请求不超过 2 秒。库给整个解析流程 4 秒上限，超时 abort 并丢弃，不重试。收到认证失效需同时通知 setSession(null)，不能仅吞掉 401。不使用当前 feed 页、事件中的名称/备注/评分、订阅别名或 handle 作替代。

| 返回字段 | 规则 |
| --- | --- |
| subscription_id / project_id | 与候选完全相同，分别 sub_UUIDv4 / prj_UUIDv4 |
| project_name | Projects 的真实项目名称，非空，最多 4000 字符；合并空白，不猜测、不截取其他字段；控制/不可见双向字符拒绝 |
| subscription_revision | 当前订阅的正 safe integer revision |
| rating | Projects 当前 S/A/B；C/D/null/missing 均返回 null 或跳过 |
| project_revision | 当前项目的正 safe integer revision |

库会再次核对投影、当前 epoch、连接、开关、静音和 TTL，但不能替代 B1、HTTP envelope 或服务端权限验证。候选只保留六个关联字段，原 payload 及正文不存入队列；metadata 仅为当前一次播放短暂使用，不持久化/日志记录。

5. 用户原生点击“启用本页语音”时控件同步调用 `enableFromGesture(event.nativeEvent)`；不在 effect/自动恢复时调用。新页面或会话需手势启用；同一页面重连可在浏览器 hasBeenActive 为真时调用 resumeAfterReconnect(identity, true)，仍受之前已启用、未关闭及会话有效限制。启用只记录用户操作，`starting` 不代表已发声；收到原生 onstart 才显示浏览器报告播放。浏览器实际许可失败则显示 failed 并停止，不偷偷重试。
6. 用 `bindVoiceBrowserLifecycle(controller)` 接 pagehide/freeze、visibility 检查和同用户 storage 变化；其返回清理函数会 destroy。B1 与 EventSource 的生命周期必须由现有 controller 显式转交，库不创建第二套信息流、HTTP 或认证逻辑。bfcache 恢复后重新验证会话与连接并重新手势启用。

## 固定行为

- 只接受 original/quote、source=wss、is_live_new=true、replay=false。SSE event_id 为 evt_UUIDv4，activity_id 接受 act_UUIDv5（B3 当前产物）及合法 v4。缺字段/未知来源/updated/历史/发现一律丢弃。
- 只播“项目名称，S/A/B级。”；仅使用 `localService=true` 本机音色，优先中文。本机音色列表为空或 API 不支持时明确不可用；不回退远程音色，不用 Mac 后台任务或第三方语音。
- 默认全局关闭，逐订阅默认允许。仅存 `ikun.voice.v1.<encoded user_id>`：version、enabled 和最多 1000 个关闭的 subscription_id。即使 enabled 已保存，新页仍 locked；无存储时只在内存生效。其他页修改偏好会清队列并要求本页重新启用。
- Asia/Shanghai 22:00（含）至 08:00（不含）静音；精确边界定时器和每次入队/开始播放重验，跨 22 点 cancel、abort、清队列。静音/关闭/断流时事件丢弃，08 点、重连或打开开关都不补播。
- 最多 20 项，含当前解析/播放；候选 received_at 必须为可靠 UTC 时间、不得晚于本机当前时间或早于启用/连接界线，30 秒内才接受/开始。时钟回退不延长已接收事件有效期，时钟偏差保守丢弃。
- 稳定 event_id 和 activity_id 各最多 1024 个、10 分钟窗口；满时丢弃新项，不驱逐尚未过期的 ID，防止拥塞下重复播放。更早的重放仍由原 received_at、30 秒 TTL、连接界线与 replay 门槛拒绝。去重仅内存；跨页不保留旧活动，依赖上述新事件门槛。
- metadata 顺序解析，4 秒超时；单次语音 30 秒无完成回调则失败并需重新启用。已提交浏览器但尚未开始的语音超过候选 TTL 会 cancel。所有失败、关闭、会话变化和断流都不影响 feed，也不自动付费重试。一次逐订阅修改会保守清掉当前队列，避免旧 metadata 晚到。

接口依据：[Web Speech 本机音色](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService)、[cancel](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/cancel)、[用户手势](https://developer.mozilla.org/en-US/docs/Web/API/UserActivation/isActive)。

## 运行验证

在本 Worktree 使用既有 Node/pnpm，依赖不变：

```sh
cd packages/ui
node --import tsx --test src/voice/tests/voice.test.mjs
pnpm test
pnpm typecheck
# 完整 build / 浏览器必须先用总管唯一 heavy lock，集成优先。
# build 成功后可直接运行编译产物轻量 smoke：
node src/voice/tests/compiled-smoke.mjs
```

独立无声浏览器夹具（在 Worktree 根目录，完整预览过程持锁）：

```sh
python3 /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/scripts/with-heavy-lock.py --owner chief-review --timeout 0 -- node packages/ui/src/voice/harness/serve.mjs
```

地址 `http://127.0.0.1:3260`。只绑定 loopback、GET/HEAD、CSP 禁止 connect/media。夹具只注入 MockSpeech/FakeClock/合成 metadata，从未调用实际 Web Speech 输出；Ctrl+C 退出释放锁。它不是正式 v2 页面验收。
