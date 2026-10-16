# Tracking 观察受理 / 回执 v1（待协议审查）

依据限定放行 `a76f17633b1a0c73e6a9cdada9db575514256c4c`。Projects基线 `aa51a640a159e4c8f6cdd841a25f4279e73075ba`；输入逐字段按Tracking `c4de379a67bd9b154bab87ce81d4645b53102ea0`核对；沿用phase2 EventEnvelopeV2 / EventReceiptV2及已批准B3/D2规则。本次仅MD+JSON，业务实现待总管审过后进行。

**已独立核实的边界**：c4de `store.py:474–500`写观察outbox；`retention.py:227–284`过期scrub；`api.py:264–277`仅GET outbox状态，无envelope/claim/ACK；全部Tracking运行源码未找到delivery/reconcile/receipt_result任务。只升级网站不能写回tracking.db，网站可完成接收与可查回执，worker状态闭环仍BLOCKED；不从SSE重建正文。

## Wire、权限、hash

- 仍为 `POST /internal/v1/ingest/tracking`、`GET /internal/v1/receipts/tracking/{evt_UUIDv4}`。schema_version=1；仅接收实际outbox的 `tracking.feed.activity.created.v1` / `tracking.feed.activity.updated.v1`，不猜tracking.tweet或旧SSE类型。原envelope十字段、payload十五字段/约束及有效样例精确列于同名JSON。
- payload为部署activity(record)+tweet_kind/replay/is_live_new。canonical project_id、sub_UUIDv4、evt_UUIDv4须合法；inner/outer项目/时间一致，correlation_id=activity_id，activity_id按B3固定namespace及[scope,sub,tweet]复算UUIDv5；安全X URL与handle/tweet一致。created只接受original/quote+wss+实时标志；updated可为REST/补全/可见性更正，含unknown/reply/repost，不通知为新推文。
- 只用已有 `PROJECTS_INGEST_TRACKING_TOKEN`，与API/Hunter/IPC/provider方向独立。无/错token及cookie单独401；已验证方向/source/scope冲突403；伪造角色头不授权。既有handler独立检查，不依赖Proxy。私有RPC拟用contract=tracking-observations-v1，仅ingest/receipt、source=tracking、principal=null；Hunter模型/contract/命令链不变，不能只移除501就调用Hunter专用模型。
- 单个完整UTF-8 JSON object，Tracking专用128KiB/有界读取（Hunter仍64KiB）；坏JSON/字段/ID/类型422。hash为SHA256(部署protocol.canonical对原已校验JSON对象的UTF-8)，与retention.original_hash一致。保留字符串/时间原表示，不先datetime model_dump再hash；对象顺序/空白无关。generation为SQLite正int64，保留超JS安全整数的原数值语义直到私有RPC，禁止浮点舍入；无效单surrogate/UTF-8拒绝，未知字段/非有限值拒绝。
- 可选私有头 `X-Expected-Event-SHA256`（64位小写hex）：POST核对计算值，GET核对已存body_hash；坏格式422、值不符409 CONFLICT。不是新方向凭据，不改Receipt DTO；未来publisher必须用原hash核验的200才能落本地ACK，已删正文时用original_hash，不重算scrub对象。

128KiB边界静态证明见 `tracking-observations-size-check.json`：20000 emoji/120 emoji名称和20000个需6字节canonical转义的控制字符分别核对完整event及RPC包装；使用最大int64、最长时间/ID/URL/request_id和hash，均低于既有IPC 131072。publisher应发送其已存canonical UTF-8字节；超限413，不截断/重造hash。控制字符是合法内容，非法单surrogate必须422，不能用replacement字符修补。

## 最小事务与受理含义

不需迁移：复用event_inbox和project_sources。BEGIN IMMEDIATE内查 `(scope,source,event_id)`，同hash返回原receipt_id/project_id/首次accepted_at、duplicate=true，异hash409；首次验证同scope canonical已存在，校验/建立 `observations-v1:subscription:{sub_ID}`→project_id关联，然后写inbox/receipt并commit，失败全部回滚。已有sub指向另一项目409，无/外scope canonical404，不注册新项目、不按handle/官网猜映射。首次关联是可信Tracking观察关联，不冒充新人工确认。

事件hash承诺原project/sub/activity/event元组，sub别名和event→project/hash均持久；不向旧receipt强加sub字段。首次POST返回200，data恰为EventReceiptV2六字段：event_id/project_id/receipt_id/accepted_at/duplicate=false/command_id=null；GET和重放duplicate=true。accepted_at由Projects写真实UTC。失败只error/request_id，无data；全部带request_id/no-store。受理不等于平台运行、公开送达或主页新事件。

**只保ID/时间/hash/receipt/关联，不存envelope/text/名称/URL/raw副本**；不修改评分/人工资料/进度/membership/revision，不写命令、project_changes或公开SSE，不抖动C03评分版本，不写其他三库。v1新增公开投影为零；原主页仍用active+S/A/B及既有ProjectRecordV2，原B3 published feed/C03负责其内容展示。hidden/removed/C/D/null不因观察自动加入。最小账本沿B2持久保留，不随Tracking正文清理删除；原schema2/校验和不变，回滚关闭新增准入但保留已受理证据。

## unknown / 过期（不伪造闭环）

| 本地事实 / 查询 | 唯一允许的结论与后续 |
|---|---|
| 完整未过期原事件，POST丢ACK/超时/重启 | 先GET原event_id+原hash；200匹配才确认历史受理，409停止自动重试。404且原body仍完整/未过期，只有原owner经TTL/lease/purge栅栏后才可同ID/hash有界补投 |
| expired_pending_reconciliation、正文已scrub，GET200/hash匹配 | 仅确认既有历史受理；原owner另行实现本地ACK写回，保留expired，不恢复内容、不新通知 |
| expired且GET404或源不可用 | 仍unknown；404不是accepted/failed/从未投递证明。只允许有界退避GET，鉴权/冲突停止并告警；不补正文、不改ID、不虚假ACK以清零pending |
| scrub后的expired对象被POST | 缺payload/多expired字段，不是完整v1，422；已有回执也只能GET，不伪造新的受理 |

原wire无全局first_received/权威expires_at；不能用新generation的received_at重推D2寿命。本域不新增内容展示或宣称已验证完整15天TTL。合法POST由Tracking原owner按原expiry及purge栅栏决定；若要接收方独立证明完整TTL，需先报最小源metadata扩展，不偷偷要求当前worker新字段。临时故障沿内部5秒/外层10秒及既有退避，429尊重Retry-After；401/403/409/422不自动POST。

## Worker最小缺口与回归

缺口仅申报：Tracking原owner在现有单实例lease内加delivery/reconcile任务、受控loopback网站目标/已有ingest token文件引用、原hash校验后的本库receipt/ACK事务与重启恢复，协调D2 purge；expired只GET。若需attempt/lease/ACK接口或迁移由该owner另报，总管单独放行。本窗口不写worker、不跨库清pending，不等待不存在的ACK设计才做网站部分。

| 回归 | 协议批准后的必要证据 |
|---|---|
| 受理/冲突 | 两种实际事件、可见性更正、Unicode/null时间、固定UUIDv5；同ID/hash重放/异hash409、并发一回执、关联冲突、事务失败全回滚、重启可查 |
| 权限/坏输入 | 真实Node/UDS入口，方向隔离、cookie/伪造头、错source/scope、坏ID/hash/URL/字段；不注册不相关canonical，不自动加入/改人工数据，其他库不打开 |
| 丢ACK/过期 | 本机丢ACK先GET不盲POST；retention原样scrub对象422；已受理过期只查旧receipt；未受理且已删正文404仍unknown、零重建/补投/假ACK |
| 兼容/交付 | 保留Hunter/B2/C03/B1回归、输入/证据hash与准确计数、子项不累加；网站能力与冻结worker阻断分开。完整build/browser确需时持原唯一heavy lock串行 |

只用本地合成夹具。总管审查后交集成按其当前网站基线前向收件/仅升级网站和既有IPC；不夹带其他业务。本owner不合并/推送/部署，不动main/ikun.ca/真实6551/REST/付费/共享Watch/旧版/既有Cloudflare；不改任何冻结worker或语音/UI成果。
