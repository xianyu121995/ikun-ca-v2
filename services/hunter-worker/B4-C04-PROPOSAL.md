# Hunter 研究 PATCH 与发现保留增量协议

协议版本：`hunter-research-retention-v1.0.0`。日期：2026-10-16（Asia/Shanghai）。

状态：**产品方案已批准，精确协议 `pending_protocol_review`；本提交仅供审查，受影响的新接口、迁移及清理任务尚未实现/验收。** 批准精确协议后再在原 Store/引擎上增量实现，不另建研究系统或 CRUD。

依据（仅 Git 对象读取，未合并协调分支）：

- 产品 D3/D4/D5、C-04：`5c208ec74429c37a51f67f04558508e7f9b2538a` 的 `docs/product/DECISIONS.md`、`DECISIONS-P0.md`、`decisions-v1.json`。
- 最新状态补充：`50ee277aed435a723aab6139bd952e709b3ad08e` 的相同三文件，政策 `product-decisions-v1.1`；B4 规则未变。D1 引用纳入已确认；D8 推荐已采纳，均不再报待产品确认。D6/D7/D8 的语音实现仍 held，本批不播发现、不实现播报。
- B4 放行：`63e8a2857241c6a76226f21435e40db9736a1e7e`；phase2：`9699375c920465b5d802e7acff17b5421203e544` 的 `docs/phase2/{API,DTO,STORAGE}.md`；Projects：`d0fdefab2aa230ebb8df856aed306d0184d362e2`；Auth 密码长度增量：`f097bd4722155d5e689b8894956391ed7e5f2fa7`。
- 本 Worktree 已提交实现基线：`bd69bbd0bba6fdc4f7c66191a839612dd53989d6`。现有 B4 代码/失败证据继续保留，未混入此协议提交；本文件不是这些未提交代码的验收证明。

相对于初稿有一项明确的响应细化：PATCH 返回下述**最小写入结果**，研究内容由既有 GET 读取。初稿建议直接返回完整 HunterDiscoveryV2，但完整响应幂等保留至少七天，会把临近发现过期时保存的研究内容继续留在回执中。最小结果可以同时满足原结果回放和七天清理。这一细化随本版本交总管审查，未经审查不改正式 DTO/根 contracts。

## 1. 路径、版本与所有权

唯一新增业务方法为 `PATCH /api/v1/hunter/discoveries/{discovery_id}`。版本由 `/api/v1` 路径和该方法选择，规范标识为 `hunter-research-retention-v1.0.0`；不添加隐式 profile、查询参数或客户端任意版本头。未来不兼容版本另行审查，不改变 v1 已保存幂等结果。

复用已有 `GET /api/v1/hunter/discoveries/{discovery_id}`、`GET /api/v1/hunter/signals` 和 `POST /api/v1/hunter/discoveries/{discovery_id}/monitoring-requests`。PATCH 不接受查询参数。discovery_id 使用 Hunter 已有稳定 `dsc_<小写UUIDv4>`；不得以 handle 或 canonical project_id 替代。

唯一业务 writer 为 Hunter，所有业务表、账本、审计、回执及清理状态在 `hunter.db`。备份仅为该库的隔离恢复副本。不得读写其他业务库、ATTACH 或跨库清理。Hunter 自有 integration 中仅保留 BFF/接线候选；正式网站、公共 UI/root/契约由原 owner 管控。本增量不修改保留的 `services/hunter-worker/ui/**`。

正式模式保持旧私有 PUT/review 及本机免密入口隔离。不能用旧 PUT 的测试结果替代此 PATCH 的授权、原子性或持久化验收。

## 2. 请求字段与合并规则

`Content-Type: application/json`；UTF-8 对象；body 最大 65536 字节，读取 timeout 5 秒。不接受空对象、数组、重复 JSON key、未知字段、NaN/Infinity、类型强转。字段直接平铺，为 ProjectFieldsV2 的非空子集，不包在第二层 `project` 中。

| 字段 | PATCH 接受值 | 清空/边界 |
|---|---|---|
| name | string | 1–120 Unicode 字符，trim 后非空；保留原文本，不接受 null |
| rating | `S/A/B/C/D/null` | null 表示未评分；不接受 `unrated`、中文“待定”或数字 |
| description | string | 0–4000 字符；空串清空，null 非法 |
| notes | string | 0–4000 字符；空串清空，null 非法 |
| website_url | string/null | 最多2048字符；http/https、合法主机，无用户密码、反斜线、空白/控制字符；null 清空，不接受空串或 javascript/data URL |
| category | string/null | 0–80字符；null 清空，不预设分类枚举 |
| progress_stage | `todo/researching/watching/participating/completed/paused` | 不接受 null；不会调用 Projects completion 或 Tracking 操作 |
| progress_percent | finite JSON number/null | 0–100；bool、数字字符串、NaN/Infinity 非法；未知为 null |
| token_date | `YYYY-MM-DD`/null | 校验真实日历日，不接受时间戳或 datetime |
| token_date_status | `confirmed/estimated/unconfirmed` | 合并后日期 null 必须 unconfirmed；有日期必须 confirmed/estimated |

省略字段保持原值；显式 null 只对允许 null 的字段生效；以当前完整研究模型合并后再执行完整 ProjectFields 校验。因此单独把日期清成 null、却留 confirmed，返回422且整个操作不写入；可以同一 PATCH 提交日期及状态。

discovery_id、project_id、x_user_id、x_handle、followers、profile_bio、signal_count、各种时间、review_state、monitoring_state、revision、actor、tenant_id、enabled、ignored 均为只读/非本方法字段，传入即422。评分只写 Hunter 本地研究快照；Projects canonical 评分仍由 Projects 唯一管理。

示例（未列字段保持原值）：

```http
PATCH /api/v1/hunter/discoveries/dsc_2ef30fbb-13de-4a22-95f3-84d67e1af814
Content-Type: application/json
If-Match: "rev-4"
Idempotency-Key: 087cd0aa-0f13-4adc-b632-55dc5d35dfc2
X-CSRF-Token: <真实会话的CSRF值>

{"rating":"A","notes":"合成协议示例，非真实项目","token_date":null,"token_date_status":"unconfirmed"}
```

## 3. 可信身份、权限和执行顺序

浏览器→网站：B1 每次从真实 session 验证有效期/撤销/禁用/强制改密，角色必须 superadmin，scope 固定 ikun-main；同源 Host/Origin/CSRF 检查适用于该 PATCH、Route Handler、实际 Action。客户端 X-Role/X-Tenant/X-Ikun-Principal/Authorization 不作为可信来源，不能穿透覆盖服务身份。

网站→Hunter：独立 HUNTER_API_TOKEN（至少32字符，与反方向/provider/session不同）及 BFF 刚验证的 AuthPrincipalV2。Hunter 验证方向和固定 scope，再验证 superadmin；仅有服务 token 不能冒充人类身份。原始 Cookie、session、provider 凭据不传给 Hunter，不写业务库或日志。Auth 被撤销后，历史幂等键也不能绕过本次授权。

顺序冻结为：传输/身份/同源 → 请求格式及 UUID key → 相同作用域成功回执回放/冲突 → 当前资源未过期 → If-Match/合并校验 → 原子写入。超管是账号管理 DTO 的唯一例外；研究响应、SSE、审计公开投影均不含 Hunter 个体归因。

## 4. revision、UUID 幂等、原子性与响应

If-Match 只接受强 ETag `"rev-N"`（N 为服务端正整数）；不支持 `*`、弱 ETag、列表或 body revision。缺失428 VALIDATION_ERROR；格式错误422；新操作陈旧409 VERSION_CONFLICT。即使字段值与当前值相同，成功的新操作也只递增一次 revision、写一次审计和一次更新事件，便于回放和并发线性化。

Idempotency-Key 必须小写 UUIDv4。作用域为 `(actor_id, ikun-main, PATCH + 规范化资源路径, request_key)`；hash 为对象 `{protocol,body,if_match}` 的规范化UTF-8 JSON之SHA256，protocol固定本版本标识。键按Unicode码点排序、无额外分隔空白、字符串不做Unicode/trim归一、不转义非ASCII。body保留省略/显式null差异；唯一数值字段progress_percent先严格验finite/非bool及范围，再转IEEE754 binary64，正负零统一为0.0，整数1与1.0均序列化为1.0。数值格式使用本服务锁定Python JSON实现的最短可回读float表示；其他数值字段不合法。字段独立校验/规范化可在回执查找前执行，依赖当前记录的完整合并校验在查找后执行。对象键序及JSON外部空白不影响hash，字符串内部空白/显式null/省略字段不同。不同合法actor的key不共用回执。

同 key、同请求先返回原成功结果及原 ETag，不再校验已递增的资源版本、不再递增/audit/发事件；本次 envelope 的 request_id 为本次请求值。异 body、异 If-Match 或异协议版本409 IDEMPOTENCY_CONFLICT。失败前未提交事务则不留下成功回执；timeout/500/DB错误后客户端保留原 key/body/If-Match 核对，不能换 key 盲写。客户端可重放同一 PATCH 得到最小结果，再用既有 GET 核对资源，不新增第二个研究 CRUD/操作查询 API。

单个 `BEGIN IMMEDIATE` 事务包括：到期/版本检查、完整研究 project_json、revision+1、updated_at、最小成功回执、私有审计、脱敏 `hunter.discovery.updated`（已有 HunterDiscoveryV2）。任一步骤失败全部回滚；回包丢失后仍返回原结果。审计包含 actor_id、action=`discovery.research.patch`、discovery_id、前后 revision、变更字段名、body hash、request_id 和 UTC 时间；不复制 notes/description/raw payload，不包含贡献猎手身份。并发不同 key 使用同一旧 ETag，最多一个成功。

成功200，响应头 ETag=`"rev-5"`、Cache-Control=`no-store`、X-Request-ID。`HunterResearchWriteResultV1` 是此增量的最小写结果，不替换 HunterDiscoveryV2：

```json
{
  "data": {
    "discovery_id": "dsc_2ef30fbb-13de-4a22-95f3-84d67e1af814",
    "revision": 5,
    "saved_at": "2026-10-16T02:00:00+00:00"
  },
  "request_id": "example-request-1"
}
```

GET 返回现有完整 HunterDiscoveryV2 及最新 ETag，浏览器据此刷新研究数据。保存后若 TTL 已到，GET404；不得把最小写结果当成仍存在的研究数据。回执自提交起至少保留604800秒，未到期回放始终返回上述原结果；到期清理回执不删除永久 Target 账本。过期发现的旧 key 仍可回放最小成功结果，**不会返回研究正文、重建发现、更新 TTL 或发事件**；新 key 一律404。回执清理后原 key 也只能404，不会复活。

| HTTP / code | 触发条件 | 自动重试 |
|---|---|---|
| 400 VALIDATION_ERROR | B1拒绝不合法Host/路径等传输来源格式 | 否 |
| 401 UNAUTHENTICATED | 无有效会话/方向凭据 | 否 |
| 403 FORBIDDEN | user、伪造身份、跨scope、CSRF/Origin不合法、强制改密未完成 | 否；B1 现有登录/强制改密响应沿用 |
| 404 NOT_FOUND | 格式合法但无该发现，或已满7天；外部不暴露账本命中细节 | 否 |
| 409 VERSION_CONFLICT | 新操作 ETag 已陈旧 | 否；保留草稿，GET核对 |
| 409 IDEMPOTENCY_CONFLICT | 已成功 key 对应不同请求 | 否 |
| 422 VALIDATION_ERROR | JSON/字段/日期关联/ID/key/ETag格式/查询不合法 | 否 |
| 428 VALIDATION_ERROR | 新操作缺 If-Match | 否 |
| 408/413/415 VALIDATION_ERROR | 读取超时/body超限/Content-Type错误 | 否 |
| 429 RATE_LIMITED | 已配置的入口限流 | 遵Retry-After，仅同 key 核对 |
| 502/504 UPSTREAM_UNAVAILABLE/UPSTREAM_TIMEOUT | 网站到 Hunter 不可达/超时 | 先同 key 核对，不能换 key 盲写 |
| 503 DB_UNAVAILABLE | 锁忙/磁盘/完整性暂不可用 | 先核对原操作，不能冒称未保存 |
| 503 AUTH_NOT_CONFIGURED | 缺方向配置 | 否，retryable=false |
| 501 NOT_IMPLEMENTED | 精确协议尚未获准/部署，或未知写方法 | 否 |
| 500 INTERNAL_ERROR | 未预期错误，结果需核对 | 否，不推定失败可重写 |

错误始终为 phase2 `{error:{code,message,retryable},request_id}`、no-store/X-Request-ID，不带数据库路径、异常 SQL、回执 body 或 Hunter 身份。

## 5. 与人工确认/Projects 的边界

PATCH 不注册 canonical、不写 Projects/Tracking、不加入主页、不发送 monitoring_requested、也不改变既有监控命令。人工加入仍只用冻结的 monitoring-requests：confirmed=true、完整 ProjectFields、If-Match、UUID key；在 Hunter 原事务生成唯一 cmd/evt/outbox，Projects 唯一返回 canonical，ACK 后仍不能宣称远端运行。

已经有确认命令时，PATCH 仍只改 Hunter 研究草稿。原命令中人工确认的 project 快照和 hash 不可变，后续 PATCH 不改写/重发原 outbox，也不覆盖 Projects 的评分/备注；再次以不同草稿请求同一目标加入监控沿既有409核对原命令。清理不能把原命令恢复成未确认、未POST或新的 cmd/evt。命令查询独立于发现是否存在，过期仍能给出最小 CommandResultV2 与原 canonical 引用。

## 6. D3：七天寿命、时钟、清理及备份

七天精确定义为604800秒，起点为第一次达到两名不同稳定 Hunter 阈值并持久创建发现的服务端 `first_discovered_at`，对应 DTO discovered_at。不是目标 profile.createdAt、最后一次关注、最后编辑或监控确认时间。旧记录迁移沿用原 first_discovered_at，不能重置为迁移时刻。

`expires_at = first_discovered_at + 604800`，有效条件严格 `effective_now < expires_at`；等于即过期。UTC整数微秒做边界比较；迁移旧REAL时间按十进制值截断到微秒，不四舍五入延寿。所有 TTL 检查、清理和测试共用同一函数。

effective_now 取 `max(当前服务器UTC, 本库持久retention_clock_highwater)`，每次运行任务/对外资源判断先原子推进 highwater；不能持久推进则503且不返回可能复活的资源。进程内 monotonic 只用于调度/timeout，不当UTC业务时间。系统时钟回拨、重启、恢复都不能降低 highwater 或清除 retired 标记；前跳可能提前到期，必须通过已核验备份恢复流程处理，不能清空账本重开提醒。一次请求/事务只取一个时钟值。

GET、signals、PATCH、人工 monitoring-request 在有效期检查上保持一致；分页 cursor 的旧快照时刻不能绕过当前 TTL。signals 仍保留 phase2 “当前72h合格聚合”筛选语义，不把七天保留偷换为新列表 profile。GET 可在窗口滑出后、七天内读取研究；人工监控仍须满足原72h合格条件。旧 cursor 遇已清理行跳过，不能返回旧响应快照；不得重设 cursor 使其从头重放。

唯一 Hunter 后台清理循环：拿到 worker lease 后即检查，其后每60秒检查一次；每事务至多500个过期发现，继续有待清理项则逐批处理并允许 graceful shutdown。无需网站打开。普通 serve/readiness 不做DDL；运行前必须显式迁移。清理失败保持持久错误/下次重试时间，只暂停删除，WSS/REST/回执恢复按原隔离规则运行。逻辑到期立即不可读/不可新写，即使备份失败导致物理删除延后，也不能重新显示。

清理必须先有可恢复且可核验的 SQLite online backup，禁止 cp 运行库/WAL。协议步骤如下：

1. 同库 maintenance/写事务与 worker lease 串行化，选择本批过期ID并固定 highwater；独立只读连接执行一致性 online backup 到 Hunter 自有私有临时恢复目录，不访问其他库。备份/验证有30秒总上限，SQLite锁忙仍受5秒上限；超时/满盘不删。
2. 验证 application_id、store identity、schema/checksum、quick_check、foreign_key_check，以及选中ID/原cmd/evt/hash/receipt/posted状态均在备份中；写manifest（协议/源构建版本、schema/hash、backup SHA256、UTC highwater、过期ID及最小稳定Target栅栏、计数）。原子rename并fsync文件/目录完成后才允许删除。目录0700、文件0600，拒绝软/硬链接；备份不能放网站公开目录。
3. 同一清理事务保留/退休Target账本、压缩恢复状态、清理过期发现/研究内容及对应旧SSE快照。提交后验证账本与未决链不丢失，记录批次计数/hash和manifest完成状态；崩溃时保留临时/未完成证据，不自动假定删除成功。
4. 备份最多保留最新3个、最长48小时，两个条件同时满足才保留；活跃清理/恢复所需bundle暂时pin，成功退出后解除。到期bundle自动清理自身备份，不能因长期保留备份变相无限留全文。容量不足且不能安全删除pin的bundle时停止新一批删除并报错，不牺牲未决恢复链。

恢复为显式命令，目标为自己空目录下的新路径 `hunter.db`，验证完整bundle/manifest后恢复，不覆盖原失败库。恢复时先应用manifest的 highwater/过期栅栏再开放API/采集，即使恢复的是清理前副本也不能把过期发现/快照重新显示或提醒。现存库若有更新的Target账本、posted意图、幂等或回执，必须以受控恢复导出把这些最小状态合并为只增的恢复栅栏；posted只可false→true，原cmd/evt/hash不能变化，冲突失败并人工核对。禁止把恢复旧库视为允许重新POST。

**裸旧SQLite副本不构成安全恢复**：如果无法证明已覆盖备份后新增的发现/POST/回执栅栏（例如当前库与其最新恢复证据同时丢失），恢复命令必须 fail closed，保持外部I/O/提醒/命令投递关闭。不能声称任意历史备份天然拥有未来去重信息。验收须覆盖可核验bundle恢复和该失败关闭路径。

## 7. D5：永久最小Target账本与清理范围

唯一永久提醒键为 `(ikun-main, platform=x, stable_x_user_id)`，与handle、generation无关。稳定ID为平台十进制字符串，保持字符串，不转浮点。首次创建发现时，在同一事务插入此键、固定 discovery_id/first_discovered_at，并写首次公开投影；唯一键冲突不能创建第二条发现或第二次首次提醒。后续字段/计数变化仍可产生现有 `hunter.discovery.updated`，这些是更新/缓存失效，不能被消费为“新发现提醒”。重放不再次通知，语音本批始终关闭。

账本每目标仅保留 scope、platform、stable_x_user_id、first_discovery_id、first_discovered_at_us、retired_at_us（可null）。expires_at由起点推导，不存可刷新TTL。退休后无研究文本、handle、profile、评分、Hunter列表/数量/归因、raw payload或原始事件。保留 discovery_id 是为了核验回执及已过期资源；retired标记防止回拨恢复。原 source_entity_key 仅在仍需映射/命令恢复的最小记录中保留，不冒充canonical。

身份仅有handle尚不能证明stable Target：不得先制造稳定ID或公开可提醒发现；只保留原有限窗口内必要观测等待可靠ID，不能新增付费查询来填值。别名必须由可靠稳定ID证据关联；不同稳定ID冲突进入核对、不误合并。迁移旧发现若缺可靠稳定ID、同handle多ID、同ID多已提醒发现则阻断迁移供核对，不删库/按handle造永久键/静默合并。此保守门槛是本协议待审实现规则，不冒称旧代码已做到。

| 数据 | 到期后的处理 |
|---|---|
| discoveries及研究project_json/旧研究列 | 删除；不可因已确认监控或PATCH延期 |
| follow_events及资料快照 | 已过72h有效窗口的观测可清理；发现到期不永久保留其Hunter归因。不能为清理发现提前删掉其他目标仍在窗口内的有效观测 |
| target_identities/aliases、seen_targets | 只留当前baseline/未决映射所需最小状态；已退休目标不再存资料或为handle复活旧发现，稳定ID账本先于别名判断 |
| public_changes中该发现的完整DTO历史 | 过期即从读取/续传排除并物理清理；不能借Last-Event-ID重放旧研究；sequence不回退、不复用，允许空洞 |
| 新研究PATCH成功回执 | 仅本协议的最小写结果/hash/key/ETag，至少自写入七天；到期后可删除，无研究正文 |
| 现有其他写回执 | 命令/账号最小结果保留原至少七天语义；迁移发现含完整业务内容的研究类旧回执须隔离审核，不能冒充已兼容新PATCH |
| audit | 仅最小actor/action/资源ID/revision/hash/字段名/时间，不保留研究正文或Hunter归因；不发布原审计给user |
| 独立命令/outbox/回执 | 按下一节保留恢复必需状态，不通过级联删除消失 |
| Projects/Tracking | 无任何访问或清理；由各owner自行处理 |

退休稳定Target的后续事件先命中账本，不重新保存过期资料/创建发现/刷新起点/产生首次提醒；仍可推进自己最小来源checkpoint。handle改名、乱序、重连/重试、窗口滑出后重新达标、删除/恢复猎手、重启、备份恢复均同样处理。不同稳定Target可分别触发一次。禁止“重新研究/重置再提醒”接口或例外。

## 8. 到期与未决人工确认/outbox的完整性

现有task_outbox外键指向discoveries，不能直接DELETE父记录或无限留下带研究全文的父记录。拟用显式Hunter增量迁移解耦：命令以原command_id/event_id/discovery_id、scope、stableTarget/source_entity_key为自己的持久引用，不再以必须存在的发现行作恢复前提；不建立跨库外键。原身份和唯一映射不改写。

| 确认状态 | 到期时恢复必需内容及动作 |
|---|---|
| 尚未形成确认事务 | 清理发现，不生成命令；与PATCH/confirm并发由同库事务线性化 |
| 已持久确认、posted=false，尚需初次发送 | 仅保留**这一份**人工确认的不可变最小EventEnvelope及原ID/hash/actor/重试状态。该body是履行未决确认必需状态，不保留发现/研究/归因的重复副本；不是借未决状态豁免所有过期内容 |
| posted=true，回执未知/在途 | 保留原cmd/evt/请求hash/posted标记/方向scope、重试和reconcile所需状态；到期可去掉已不再用于POST的项目正文。只能查原回执，不因404/恢复/过期再次POST |
| Projects已受理/已有receipt | 保留原canonical/receipt/accepted_at/command最小投影与去重hash；删过期body及发现全文。受理不等于Tracking正在运行 |
| 已确定终止的失败 | 保留最小失败结果/hash/审计及规定幂等期限，不留不再用于恢复的body；本增量不提供改key重新确认过期发现的旁路 |

posted意图必须先于网络发送持久化。压缩不能把posted变回false或把unknown改成可盲POST；failed/unknown的状态语义不因TTL自动改成succeeded。原始未POST确认body仅在仍必须履行该原确认期间保留，首次进入posted/reconcile后即满足压缩条件；状态停滞应显示持久错误供核对，不延寿完整发现。既有投递超时/次数/预算策略沿用，不能以清理为由扩大重试或付费。

命令完成/回执恢复必须允许父发现已不存在：只发布最小command.updated，不重新调用完整discovery DTO来重建已清理发现。迟到正确回执可更新原命令canonical/receipt；错event/command/project或hash继续冲突隔离。

## 9. D4：停用、窗口与恢复基线

有效观测以**停用事务提交前已受理**为界；只要其原window_at仍满足 `effective_now-259200 <= window_at <= effective_now`，即使所属猎手现已停用/删除也继续计数，禁止在聚合SQL中JOIN enabled过滤掉它。到72h恰好边界仍计数，严格超过才退出；不同来源/多次关注仍按不同稳定Hunter ID计数，单Hunter重放不能满足两人阈值。

停用/删除与事件受理均在同库事务中检查当前enabled/deleted/generation；停用提交后，WSS与REST旧generation在途结果全部丢弃，不借旧发生时间补入。先发生但从未受理、停用后才到达的包不追认；这是保留当前generation安全边界，不能伪装为补齐全部历史。与停用同一UTC时间的事件按事务提交先后决定，不能只比较浮点时间。

恢复/重新添加沿用稳定Hunter身份和既有有效历史，但递增generation并先建立新baseline。REST第一轮只做baseline；WSS新代只在真实订阅ACK后建立baseline，ACK不是来源心跳。未baseline/旧代结果不得当新增关注。保留历史不意味着恢复后把最新20条旧关注再次视为新增。

**缺可靠关注时间仍未被产品裁定。** 本轮维持已验证来源策略：WSS必须有合法外层事件createdAt（不以profile.createdAt或接收时间填假发生时间），缺失/非法拒绝；REST无可靠关注时间，只把baseline后首次观察记录为first_observed_after_baseline，明示它不是真实follow发生时间、最新20条/断档可能遗漏。本增量不把该近似升级为最终产品窗口政策，验收报告单列限制。

## 10. 迁移、兼容和回滚

拟在现有B4 schema3候选之上增加 `schemas/hunter/004_research_retention.sql`（版本/文件名随本协议审查；此提交不创建SQL/修改registry）。只允许显式migrate/init；先成功备份并校验，再在单事务中新增Target账本/时钟/清理批次状态及命令自有恢复引用、重建所需外键。foundation1、原2、B4候选3及其哈希不重写，checksum仍归同一registry，INSERT显式列名。

回填全部已有发现的稳定Target键/原discovery_id/起点，包括已滑出72h但未满七天的发现。重复/缺失稳定身份不猜测，整个迁移回滚并报告核对阻断。已有超过七天的记录回填账本并逻辑到期，但物理清理仍必须经过可核验的清理备份；迁移不能借重建表提前丢未决链。

已到期记录与既有正确cmd/evt/receipt/幂等/hash/posted意图逐项比对迁移前后；已有旧未定协议任务维持原review-required隔离，不转换成新正式任务。受支持三/四列_schema_migrations兼容、application_id/owner/checksum/未来版本拒绝沿用；DDL失败/中断回滚，无serve/readiness自动修复。

新二进制拒绝未迁移库；旧二进制必须拒绝schema4，不能带着不认识的退休语义运行。回滚采用新路径恢复bundle+栅栏并配兼容二进制，禁止降版本号/删ledger/直接回放旧库以恢复服务。恢复无法证明新栅栏完整时保持fail closed，而非宣称回滚成功。

HTTP旧GET/分页/monitoring-request DTO与SSE枚举不改；新PATCH使用最小结果，消费者在审查批准后按最小接线修改。所有读均no-store；保存后使当前detail/signals及同源缓存失效，再用既有GET取最新；HTTP409保留草稿，写入未知保留原key锁定核对，不回退demo。清理后的旧SSE快照不得再发，命令SSE仍正常；新发现提醒按稳定账本及首次discovery_id去重，不把研究updated事件当提醒。

## 11. 裁定覆盖表与验收计划

以下均为**计划，运行时结果pending_owner_implementation**，不能引用历史130项Python/9项Node/构建或OS smoke证明本增量已通过。协议获批后补实际实现完整SHA、命令、计数和证据；协议提交SHA以Git对象及交付短报为准。

| ID | 协议条款/计划用例 | 当前状态 |
|---|---|---|
| DEC-C04 / C04-01 | §1–4全部字段min/max/空/null/非法/未知/日期关联，非空subset合并；真实刷新GET持久化 | pending_owner_implementation |
| DEC-C04 / C04-02 | 匿名/user/伪造角色/错方向/跨scope/禁用/强制改密/撤销、Route Handler绕过Proxy、实际Action及同源CSRF | pending_owner_implementation |
| DEC-C04 / C04-03 | 缺If-Match428、格式422、旧版本409；同key重排字段、1/1.0及-0/0规范化回放，异body/If-Match409，actor/route隔离 | pending_owner_implementation |
| DEC-C04 / C04-04 | 两请求并发、事务中断/kill、提交后丢回包；研究/revision/audit/receipt/SSE恰好一次或全回滚 | pending_owner_implementation |
| DEC-C04 / C04-05 | 当前draft与已确认immutable命令分离；不新增canonical/POST/outbox；审计/SSE/日志无Hunter归因或正文泄露 | pending_owner_implementation |
| DEC-C04 / C04-06 | 临近7天PATCH不延TTL；过期新key404、旧key原最小结果，无正文/复活/事件；回执自身七天边界 | pending_owner_implementation |
| DEC-D3 / D3-01 | 604800秒前1微秒/恰好/后1微秒；编辑/重放/确认不延寿；后台定时且网站关闭也清理 | pending_owner_implementation |
| DEC-D3 / D3-02 | 备份成功/权限/软硬链/锁忙/满盘/超时/校验失败；失败不删、逻辑到期不再读；3份/48h和pin边界 | pending_owner_implementation |
| DEC-D3 / D3-03 | 清理前备份恢复到新路径、manifest栅栏、时钟回拨/重启；裸旧备份/证据不全fail closed | pending_owner_implementation |
| DEC-D3 / D3-04 | pending未POST/posted未知/丢ACK/正确及错回执/终止失败在7天边界前后；原cmd/evt/hash/receipt/posted不丢，不盲重发 | pending_owner_implementation |
| DEC-D3 / D3-05 | 清理发现、project_json、旧列、DTO/SSE全文；账本/audit/最小回执字段白名单；不得保留全量原始数据冒充账本 | pending_owner_implementation |
| DEC-D3 / D3-06 | 非Hunter合成哨兵文件前后hash相同、捕获文件访问/SQLite authorizer无他库路径、ATTACH或跨库SQL | pending_owner_implementation |
| DEC-D4 / D4-01 | A停用前有效+B后关注达标；A历史72h前/恰好/之后，停用/删除不提前剔除 | pending_owner_implementation |
| DEC-D4 / D4-02 | 停用事务与WSS/REST在途竞态、旧generation/发生时间伪装；停用后不接新事件，双稳定Hunter才达标 | pending_owner_implementation |
| DEC-D4 / D4-03 | 恢复先baseline、REST20条旧目标不算新增、WSS ACK非心跳；缺时间按来源现行策略且报告待定 | pending_owner_implementation |
| DEC-D5 / D5-01 | 同目标初次达标一次首次发布；追加关注/窗口滑出再达标/7天清理均零新增提醒 | pending_owner_implementation |
| DEC-D5 / D5-02 | handle改名/乱序/重放/新代/重启/备份恢复仍同稳定键；不同稳定ID独立、冲突不合并、未知ID不假造 | pending_owner_implementation |
| DEC-D5 / D5-03 | 永久账本不含Hunter归因/资料正文；研究updated及Last-Event-ID重放不当成新提醒，无重置例外 | pending_owner_implementation |
| MIG-01 / HUN-04 | 空新库、foundation→2→3→4、重复迁移、三/四列ledger、失败回滚/备份恢复、身份歧义阻断和旧binary拒绝 | pending_owner_implementation |
| AUTH/PRO/ISO/OPS | 仅local synthetic来源；四库由各owner持有，整链路/C0另验；1440/390接线回归在共享heavy lock完整生命周期内 | pending_owner_implementation |

重任务只使用主仓库唯一 `scripts/with-heavy-lock.py --owner hunter-worker --timeout 600 -- <前台命令>`，构建和预览全生命周期串行；不并跑、不改锁、不停止他人进程。不调用真实6551/REST/付费API，不动Watch，不合并/推送/部署。

本轮文档检查及受保护UI哈希检查见 `python/docs/b4/product-protocol-review.json` 与 `product-protocol-check.txt`；这些是文档/边界检查，不是上表运行时PASS。

## 12. 初稿历史（2026-10-15，已由本版本状态/细节取代）

初稿为“C-04 最小增量提案（待裁定，未实施正式写路由）”，建议同一路径、ProjectFields非空子集、可信superadmin/固定scope/CSRF、If-Match及至少七天UUID幂等、同库事务/审计，并建议完整HunterDiscoveryV2响应。它明确不注册canonical、不发监控，正式写入口保持关闭。产品推荐方案现已批准；仍待的是本版本精确协议审查及后续实现验收。旧“待产品裁定”和“完整响应”不再代表本次提案。
