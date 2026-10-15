# ikun.ca 独立 NEW_TWEET 引擎 · B3 v4

独立Tracking进程，仅写DATA_ROOT/tracking/tracking.db。网站退出/重启不会停止引擎、去重与保留期作业。默认外部采集关闭，不复用旧服务、账号或共享Watch。

夜间协议与构建已获明确放行。当前按NIGHT-HANDOFF.md实施/验收，最终计数、完整SHA及绑定证据以NIGHT-EVIDENCE.json为准；原B3-REVIEW/B3-EVIDENCE保存旧阶段与失败历史，不能当最新结果。主站合入、部署与新作业归总管/集成，本窗口不执行。

## 能力

- 超管人工确认后经固定B1/B2真实guard/IPC受理；user只读。Worker不持人类会话，不读其他领域库，服务方向token独立且至少32字符。
- 稳定sub_ID与command inbox/hash/幂等/revision；启动、停止、恢复、移除需远端实际读回，ACK/本地desired/超时不是成功。NEW_TWEET最多600名额，满额报错并退避，不自动踢账号。
- WSS订阅ACK/pong/断线重连、REST最近100条有界恢复、租约/崩溃重启；已有归属/分组/全部flags不符即阻止平台修改。真实来源仍关闭，connected不能被本地进程心跳冒充。
- published-v1全量服务端搜索、S/A/B筛选/计数、发布时间倒序及接收时间回退；60秒ID快照、绑定用户/语义/评分版本的HMAC游标，limit可变。C03仅BFF经既有Projects UDS读权威评分，再将投影交本Worker，无新token/服务/回调HTTP。
- 原创和可靠引用纳入；回复/转推/未知隐藏，引用对象不参与过滤，已知X ID优先验证作者。独立NEW_TWEET_QUOTE本地映射获审，见D1-ADAPTER.md；未做真实provider端到端。
- 全局永久小tweet账本，跨代公开活动按sub+tweet折叠；补采、重放、补全文、类型补全不再产生新推文通知。15天UTC固定寿命，过期先隐藏，验证备份后分批清除所有正文/SSE/outbox副本；命令、幂等、必要回执状态保持。
- 首次激活前持久ready=0的显式新路径恢复；合并独立非退回账本、清理、校验后才ready=1。旧SSE锚点422，旧快照失效。备份过时的控制状态不得覆盖新备注/命令。保留时钟用原子MAX，回拨不复活。

## 运行

Python3.11+、Node24及固定B0 runtime。第三方依赖用requirements.lock.txt；独立release必须包含源码及仓库schemas/tracking，不从Worktree、.b3/preview或旧服务cwd运行。Nodecompiled入口会用绝对entry.py、私有配置目录cwd与裁剪环境启动Python，强制外采关闭。安装/构建仍通过主仓库唯一heavy lock。

```sh
/ABS_RELEASE/services/tracking-worker/python/.venv/bin/python /ABS_RELEASE/services/tracking-worker/python/entry.py init --config /ABS_PRIVATE_JOB_CWD/tracking.json
/ABS_RELEASE/services/tracking-worker/python/.venv/bin/python /ABS_RELEASE/services/tracking-worker/python/entry.py serve --config /ABS_PRIVATE_JOB_CWD/tracking.json
```

已有库只用显式migrate，v3先验证备份再升004；API/worker/serve/ready不执行DDL。backup/status/restore/clock-check命令、环境、Node服务入口与预检详见NIGHT-HANDOFF.md。配置0600、job cwd0700且无.env；token_file空、remote_enabled=false、dedicated_account=false。生产launchd例子仅提供，未安装。

## 接口

公开候选均由B1 guard保护，标准data/request_id、no-store。超管业务写仍要求Origin/Host/CSRF、UUID Idempotency-Key，修改/状态动作If-Match；本Worker只收服务方向凭据和可信BFF actor，不接受浏览器身份头。

| 入口 | 功能 |
|---|---|
| /api/v1/tracking/subscriptions | 查询/人工确认创建；子资源查询/PATCH/DELETE，start/stop/resume异步动作 |
| /api/v1/tracking/latest?profile=published-v1 | 新全量发布时间信息流；q/ratings/subscription_id/from_at/until_at/cursor/limit |
| /api/v1/tracking/latest、activities | 旧DTO及排序方向保留；过期正文均不返回 |
| /api/v1/commands/cmd_ID | Projects真实NOT_FOUND后回查Tracking原command_ID，不盲重发 |
| /api/v1/events/stream | Tracking事件候选；标准envelope、quiet撤销、Last-Event-ID；多源正式组合由集成owner负责 |
| /internal/v1/feed/bases、snapshots、pages | 仅独立服务方向token；普通用户仅可派生查询缓存，不新增业务写权 |
| /health/ready、/internal/v1/status | 本库/进程检查；schema、外采关闭/source_state及内部保留期状态，均不证明真实来源交付 |

观察outbox仍pending可查：B2 ingest/tracking=501，未伪造receipt。过期未决观察只保留标识/hash/必要回执信息，不再投递正文；commands恢复与租约独立。

## 验证

```sh
.venv/bin/python integration/sync-b3.py
.venv/bin/python integration/bind-b3.py
.venv/bin/python -m pytest -q
.venv/bin/ruff check tracking tests integration --select E4,E7,E9,F,I,UP
```

Node子项含在pytest wrapper中，不重复累加。loopback/UDS测试仅私有临时库/MockTransport。完整构建、compiled与Chrome整个预览生命周期必须由主仓库唯一with-heavy-lock.py串行，不能另建/删除锁。真实6551/付费来源/Watch、跨worker公网与生产接线未验证。页面如实显示“未连接真实来源”；夹具网站另设IKUN_TRACKING_FIXTURE=1显示“本地验收夹具”。语音未实现，冻结后归UI addon。
