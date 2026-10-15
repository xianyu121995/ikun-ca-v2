# B3 feed / type / retention 增量协议提案 v1.0.0-proposal.1

**状态：pending_protocol_review；不是实现或验收通过。** C-01/C-03/C-05 的方案已经批准，当前等待精确协议审查及 C-03 双 owner 对齐，不再标记为等待产品裁定。受影响的新接口、迁移和清理尚未执行。未受影响的旧 B3 回归/浏览器缺陷继续前向修复。

权威：`50ee277aed435a723aab6139bd952e709b3ad08e` 的 `docs/product/DECISIONS.md`、`DECISIONS-P0.md`、`decisions-v1.json`，政策 `product-decisions-v1.1`；前增量 `5c208ec74429c37a51f67f04558508e7f9b2538a` 作为历史保留。phase2 为 `9699375c920465b5d802e7acff17b5421203e544`，B2 已验源码 `d0fdefab2aa230ebb8df856aed306d0184d362e2`。本提案仅写自有路径；根契约、Auth、Projects、正式网站与公共 UI 不改。

## 1. 兼容与启用

公开选择器：`GET /api/v1/tracking/latest?profile=published-v1`。显式 profile 返回本文 FeedPageV1；没有 profile 的 latest 继续接收时间倒序，activities 继续原增量升序，旧 DTO 不加必填字段。未知 profile、旧 cursor 搭新 profile、新 cursor 搭旧 profile 均422。D2 生效后所有公开查询均不返回已过期正文，但旧接口的排序、ID、分页方向和字段定义保持不变。

新 profile 的 BFF/controller 候选仅在本模块 integration；正式接线仍由集成 owner 接收。新 profile 必须在批准协议、C-03依赖实现、显式 schema v4 迁移与本地验收后启用，默认不以未实现接口替代旧页。启用状态与政策版本可查询，不能把旧仅原创过滤算作新 D1 完成。没有新的进程、通信总线或付费数据源。

## 2. D1 类型与作者

规范化输入新增 `tweet_kind: original|quote|repost|reply|unknown`、`type_evidence_version` 和 `author_verified`，属于 Tracking 采集模型，不塞进旧公开 DTO。分类只取可验证的结构字段/事件类型；正文前缀、关键词、有没有链接都不构成类型证据。

| 输入事实 | 新 feed 行为 |
|---|---|
| 可靠确认发布者为被追踪账号，原创 | 显示 |
| 同上，引用自己 / 其他追踪账号 / 未追踪账号 | 三类都显示，不按被引用者身份过滤、不为此查询被引用者资料 |
| 纯转推、回复（含引用式回复） | 不显示；reply/repost 事实优先于 quote 标记 |
| 类型缺字段、矛盾或无法可靠确认 | unknown，不显示、不伪装原创 |
| 发布者无法确认或与被追踪账号冲突 | 不接纳为该账号推文，不写可污染去重账本的伪造归属 |

发布者优先用已知 X 稳定 ID 对照；本地缺稳定 ID 时，要求正文作者字段与已确认 handle 严格规范化匹配，不能仅相信外层 twAccount。引用目标未知不妨碍已可靠确认的 quote 分类。允许类型但发布时间未知，与 unknown 类型完全不同：前者显示并明示接收时间回退。

作者已确认、类型 unknown 的观察可在15天内隐藏保存，以便后续可靠结构补全。unknown→允许类型只产生 metadata_update/可见性更新，不重新产生“新推文”事件；补采、重放、正文补全同理。首次已知允许类型的实时观察才有资格产生一次新活动事件；REST恢复不补通知。

实现前须固定 WSS/REST 原始字段到本模型的映射与脱敏样本/官方资料。缺可靠字段一律 unknown。不得猜 6551 字段、增加未经审查的事件 allowlist/Watch flags，或借引用纳入修改共享 Watch。若现有 NEW_TWEET/REST 通道不能证明覆盖 quote，单列 `pending_adapter_evidence`，不得把规范化夹具当真实采集覆盖。

## 3. D2 精确寿命

单位为 UTC Unix 毫秒，15天固定为 `1,296,000,000ms`，不是本地日历日。首次持久收到时记 R；若有可靠且不晚于 R 的发布时间 P，`origin=min(P,R)`，否则 origin=R。`expires_at=origin+15d`。后续可靠补全得知更早 P 时只可缩短 expiry，永不延长；未来/无效发布时间按未知处理并保留解析诊断。重复接收、正文更新、暂停恢复、新 generation、重新创建订阅均不能刷新 R/expiry。

`now < expires_at` 可见；`now == expires_at` 已过期；过期即使删除任务因备份失败暂停，也不能再由公开读接口返回正文。首次接收到本已过期的历史推文只记最小账本，不写正文或活动事件。

保留时钟 `retention_now=max(数据库已持久的last_retention_now, 当前UTC wall clock)`，回拨不能使已过期对象复活或延长 TTL。运行中 wall clock 相对 monotonic 的偏移跳变超过300秒则记录 `clock_anomaly`，暂停物理清理并告警，不能靠重启清除异常标记；修正时钟后恢复检查。UTC时钟有效是运维前提，不声称能推断任意离线时钟错误。测试用注入时钟覆盖回拨、边界与异常。

## 4. 最小账本、跨代折叠与事件

新增本库最小永久账本，以 `tweet_id` 为唯一键（本站固定 ikun-main、来源固定 X；不以 handle/generation 作键）。允许保留：首次观察序号 first_seq、固定 expires_at、origin_subscription_id、投影状态 unknown/visible/expired。过期后可清除 origin_subscription_id；永久只留下去重/恢复必需标识与状态，不含正文、媒体、notes、raw、猎手身份。序号用于备份水位及恢复核对，不是前端 cursor。

- 首次合法观察原子写 ledger、分代观察和相应事件/outbox；崩溃不能只写一半。
- 同代重复只补全缺失字段。跨代在15天内保留分代观察语义，公开 feed 按 `(subscription_id,tweet_id)` 一条，正文取同组最新可靠非空值，首次时间与 expiry 不变。
- 新建不同 sub_ID 不能绕过全局 tweet_id 账本：已见 ID 不产生第二份公开新活动；已过期/正文已清理的 ID 不再写回正文、不复活、不重播。正常停止/恢复沿用原 sub_ID。
- 活动 ID 固定为 `act_` + UUIDv5(namespace=`c018deb2-7ccf-5092-8112-b5c9f71d40be`, name=紧凑JSON `["ikun-main",subscription_id,tweet_id]`)。namespace 来自 UUIDv5(URL namespace, `https://ikun.ca/contracts/tracking-feed/v1`)，无需网络。body/source/generation/排序时间均不参与 ID。旧分代 activity_id 不重写。
- 首次实时允许类型只写一次版本化 `tracking.feed.activity.created.v1`；补全/类型纠正为 `tracking.feed.activity.updated.v1`。事件同样使用标准 data/request_id、稳定 evt_ID。SSE replay/REST恢复标记 replay，不成为新事件；初次连流及 Last-Event-ID 重放均不能重新通知。这里只实现事件幂等，语音保持 held。
- 旧活动查询仍保留 generation、旧 activity_id；新增折叠只适用于显式 profile。已过期旧 SSE 活动载荷清除后，未知/失效 Last-Event-ID 按既有422处理，客户端重新查询当前 feed，不补造历史事件。

## 5. C-01 查询、排序与游标

新 profile 只接受：profile、q、ratings、subscription_id、from_at、until_at、cursor、limit；拒绝额外/重复参数及客户端 actor/tenant。q 为0–120字符，NFKC+trim+casefold，百分号/下划线按普通字符，搜索真实订阅备注、名称、handle与规范化正文。ratings 用单个逗号分隔参数表示 S/A/B 非空集合，规范化去重排序，默认 S,A,B；C/D/null 不伪装成 S/A/B。subscription_id 为 sub_UUIDv4。时间为真实有效、末尾Z、最多毫秒精度的 UTC ISO8601，区间 `[from_at,until_at)` 作用于下述 sort_at；未指定不额外缩短15天存储窗口。limit默认50，1–100；时间范围反向422。

全量流程：本库未过期且非已核验移除的观察 → `(sub,tweet)`折叠 → q/sub/time → D1类型 → 权威评分 → S/A/B选项 → 全量排序/计数 → 分页。stopped订阅的15天历史仍可见；remove只有远端absent且命令succeeded后才排除，失败/unknown不假装移除。

`sort_at=occurred_at ?? first_received_at`，DESC；相同时间以稳定 activity_id 的ASCII字节序DESC。DTO给 `sort_basis=occurred_at|received_at`，未知发生时间保持null，不能填成发布时间。排序、筛选和统计都在服务端完成，禁止只排序浏览器一页。

首次查询创建短期物化 ID 快照：freeze ordered activity IDs、normalized query hash、notes/eligibility semantic revision、ratings catalog_version、政策、as_of和过期时间；不复制正文。新到达的观察排在当前快照之外，下次刷新才进入；修改现有排序/类型/备注/可见性、保留期清理或评分版本改变则使旧快照409失效，不能静默拼接两版页面。

cursor为version1、HMAC-SHA256签名、不透明base64url，绑定 profile/snapshot/tenant/用户摘要/query hash/政策/数据语义版本/评分版本/expiry/下一个ordinal。签名键在显式迁移时生成于tracking.db，0600保护，不使用 provider/服务凭据、不出日志或浏览器。limit不参与绑定，因此50→10等页大小变化仍按冻结ordinal继续，无漏重。q/ratings/sub/time/profile/scope不同则422；跨用户未知快照404；正常过期/源版本变化409 VERSION_CONFLICT。

快照寿命从basis创建起60秒，读页不续命；basis准备限15秒。仅ID及短期评分缓存，重启可从本库恢复同一有效快照；显式恢复数据库后全部旧快照失效。每站点最多8个活跃快照、每个最多100000条折叠ID/10000个项目、总临时缓存64MiB；超固定查询上限422，临时容量429+Retry-After，均不返回截断的“全量”结果或假total。

## 6. C-03 最小 Projects 协同（请求对齐，尚未冻结）

只沿用网站已有 ManagedProjectsIpc / B2 UDS 方向 token、build SHA与600/700权限核验。BFF每次先用B1实际guard取得AuthPrincipalV2；普通用户可读，禁止透传浏览器身份头。Worker不持有Projects socket凭据，不打开projects.db，不拥有评分写权。BFF把已授权评分只读结果交给本库短期查询快照；这是派生缓存，不是新评分主库。

建议精确 RPC（需Projects owner确认路径/字段及全局版本）：

```json
{"operation":"ratings","contract":"tracking-ratings-v1","request_id":"req_1","principal":{"user_id":"usr_example","tenant_id":"ikun-main","role":"user"},"body":{"project_ids":["prj_550e8400-e29b-41d4-a716-446655440001"],"expected_catalog_version":null}}
```

只读响应 data 为 `{contract:"tracking-ratings-v1",catalog_version:string,checked_at:UTC,items:[{project_id,state:"found"|"missing",rating:"S"|"A"|"B"|"C"|"D"|null,revision:positive_integer|null}]}`，外层标准request_id。found必须有真实revision，rating=null表示真实未评分；missing的rating/revision均null，不能把接口失败当missing。返回项集合必须与请求相等，不允许重复或省略。

每批0–200个唯一canonical ID；空批仅取得当前全局catalog_version。catalog_version是1–128字符不透明字符串，必须随当前scope全部评分/项目存在性变化，不是当前页指纹；跨批 expected_catalog_version 不一致409。内部如何生成版本由Projects owner定，不授权B3改其schema。首批取得版本，后续批均带相同expected值；批量并发≤2、每调用2秒、整次feed8秒。checked_at距Worker当前时间不得早于15秒或晚于5秒。创建期间版本变化允许最多一次只读重取；不做付费fallback。C-03最终必须由两个owner的具体SHA对齐后冻结。

首屏对全部候选及监控统计所需project IDs取权威评分，不能先分页再查评分。每个后续页面用空批查当前catalog_version；发生变化返回409要求新查询。新建快照不使用过期评分缓存；当前快照60秒内仅在版本核对通过时复用。Projects超时/不可用/格式错/缺批返回503、无items/total/cursor，UI保留旧页并明示过期；不能猜评级、补0、退成当前页过滤。已知C/D/null/missing可排除并分别计数。

## 7. BFF → Worker 派生查询协议

沿用TRACKING_API_TOKEN独立方向及固定scope，新增内部读投影入口，不改commands协议。所有对象strict，额外字段422；可信actor来自BFF当次B1 guard，user/superadmin均可执行查询缓存，不得借这些入口修改订阅、评分或平台任务。普通commands body仍64KiB；仅以下派生接口最大2MiB、读取5秒上限。

| 入口 | 精确输入 / 输出 |
|---|---|
| POST /internal/v1/feed/bases | `{schema_version:1,actor,profile:"published-v1",query:{q,ratings,subscription_id,from_at,until_at}}`；query五字段均必填，省略的公开筛选规范化为q空串/ratings默认/其余null；200 data `{basis_id:fbs_UUIDv4,as_of,expires_at,semantic_revision,project_ids:[prj_ID],query_hash}`，捕获全量候选ID与本地真实备注版本，不把正文发给Projects |
| POST /internal/v1/feed/snapshots | `{schema_version:1,actor,basis_id,query_hash,limit,ratings_snapshot:{contract,catalog_version,checked_at,items}}`；limit为1–100；验证actor/basis/项目集合/新鲜度/语义版本及15秒准备上限，200返回首个FeedPageV1；评级仅短缓存，不提供业务PATCH |
| POST /internal/v1/feed/pages | `{schema_version:1,actor,cursor,limit,verified_catalog_version}`；BFF当次空批校验后提交，核对全部绑定版本，200下一FeedPageV1；旧rating不得由客户端声称为已核验 |

首次公开GET的limit传给snapshots，后续由pages传入；所有上述成功均是读取/派生缓存结果，不是CommandResult、远端启动回执或新的业务写权限。BFF不把这三个内部入口公开，不接受用户提供评分数组/basis/actor。候选及监控统计均无项目ID时无需评分请求，确定的空结果返回0并标记该快照评分来源not_needed（snapshot.ratings_catalog_version为null）；这不是把源失败当空结果。站点关闭不影响独立Worker采集或清理。

## 8. FeedPageV1 / 计数

响应仍 `{data,request_id}`、no-store。data严格包含：`profile:"published-v1"`、`policy_version:"product-decisions-v1.1"`、`snapshot:{snapshot_id:fsn_UUIDv4,as_of,expires_at,ratings_catalog_version:string|null,ratings_source_state:"verified"|"not_needed"}`、`items:FeedItemV1[]`、`next_cursor:string|null`、`matched_total:integer>=0`、`activity_counts_by_rating:{S,A,B}`、`subscription_counts_by_rating:{S,A,B}`、`excluded:{reply,repost,unknown_type,C,D,unrated,missing_project}`（均实际整数）与 `count_scopes:{activities:"filtered_feed",subscriptions:"all_visible_subscriptions"}`。

activity计数：经过q/sub/time、D1与折叠后，在选择ratings之前按S/A/B统计；matched_total为选择ratings后的全量活动数。excluded的reply/repost/unknown_type在折叠与q/sub/time之后、D1之前计，C/D/unrated/missing_project在D1之后、所选评级之前计。subscription计数：全部未核验移除的真实订阅，包含无推文/已停止账号，不受当前页/q/time影响；因此首屏评分批还包含这批订阅的项目ID。缺值项不混作未评分；source失败整页503，不伪造任何计数。

FeedItemV1严格字段：

| 字段 | 类型 / 来源 |
|---|---|
| activity_id / subscription_id / project_id / tweet_id | 上述稳定UUIDv5 / 原sub_UUIDv4 / canonical prj_UUIDv4 / 1–40位十进制字符串 |
| name / x_handle / notes | Tracking本地真实名称、已确认账号及备注；notes空串仍为空，不用project_name替代 |
| rating / rating_revision | 权威S/A/B，真实正整数revision；C/D/null不在当前items中 |
| tweet_kind | original或quote，引用目标身份不参与显示判断 |
| text / url | 规范化正文（≤20000字符）、安全X原文URL；不含raw/私有provider URL |
| occurred_at / received_at / sort_at / sort_basis | UTC或null / 首次接收UTC / 有效排序UTC / occurred_at或received_at |
| media / interactions / important | 缺权威来源均null，不伪造0/false；本增量不开放重要标记写权 |

语音不在此DTO中实施。UI备注须在账号/正文之前；评级、搜索、统计和分页切换到服务器结果，不能再以页面内过滤冒充全量。

## 9. 错误与权限

使用现有 ErrorCode/envelope：匿名401；普通用户业务写403；错scope403；参数/坏cursor/错profile422；未知或非本人snapshot404；版本/过期409 VERSION_CONFLICT；临时快照容量429；Projects超时/不可用503 UPSTREAM_UNAVAILABLE；本库异常503 DB_UNAVAILABLE。失败不返回部分成功data。GET不执行平台副作用，不引入客户端自动业务重试。现有CSRF/If-Match/幂等写规则不动。

当前本地Next组合的认证500另见 `python/AUTH-NEXT-BLOCKER.md`；新接口不能绕开该阻断或用独立登录补洞。B1原基线与已批准密码10增量f097bd4分别记录，不引用浮动Worktree。

## 10. 显式迁移、清理与备份

仅提议新增004迁移，不修改001–003已交付SQL。先按现有安全路径/owner/checksum检查，备份v3，再显式migrate。新增ledger、类型证据/固定expiry、feed语义版本/签名键/短期快照及retention job状态。扫描tweets与tweets_legacy为所有已存在tweet_id补账本，取最早时间及最短expiry；缺类型证据迁为unknown，新feed隐藏，不能凭旧文本猜原创。旧ID/seq/commands/receipts/审计保留。普通serve/readiness不DDL，v3旧binary拒绝v4，不自动降级。

自动清理由独立Worker现有单实例租约托管：启动立即检查，其后每300秒，单任务、每事务≤1000个tweet ID；一次verified备份覆盖其水位内的多个小事务，不为每1000条重复做全库备份。任务状态 scheduled→backing_up→verified→deleting→completed；失败→blocked_backup/clock_anomaly，记录错误和退避60秒至30分钟。网站关闭不停止任务。未获verified备份绝不删除正文/分代内容；短期无正文的派生缓存可正常到期回收。

备份仅在本库命名空间 `DATA_ROOT/tracking/backups/<job_id>/tracking.db`，目录0700/文件0600；同库SQLite backup API分块、取消检测，完整性/foreign_key/schema/ledger水位检查后SHA256、fsync、原子封存。manifest只存schema、policy、时间、哈希、水位与计数。部分备份不当成功。只保留最近2份成功备份且最长24小时，总上限1GiB；容量/磁盘不足时停删告警，不能清掉唯一可恢复副本后继续删。manifest属于已授权备份元数据，不是第二业务存储。

删除集合固定在已验证备份水位内，复核 `expires_at<=retention_now` 后同事务清除：tweets各代正文、tweets_legacy副本、expired活动SSE payload、tracking_outbox中的正文/raw副本及相应短期feed缓存。不能只删主表留下JSON全文。outbox保留原event_id/hash/关联ID/回执/必要恢复状态：已过期未决观察标为expired_pending_reconciliation，只可查询原receipt，不能再投递已过期正文；不伪造accepted/failed，不删除未决commands、幂等、审计和远端恢复状态。SSE正文过期后的旧anchor按既有失效规则处理。清理后的ledger永不删除，重放只命中抑制状态。

恢复使用显式本库restore流程：先校验封存备份；保留/合并现存库或最新已验证副本的ledger高水位，禁止较旧副本倒退ledger；在新路径验证schema/账本/expiry/完整性，轮换查询快照epoch，使旧cursor失效，再启动Worker，先过滤/清理过期内容后开放feed。复制旧DB但丢失最新去重水位不属于受支持恢复；无法证明水位时拒绝激活，不宣称任意灾难后的零RPO。备份之后尚未进入任何可恢复副本的数据不承诺恢复；测试必须覆盖已清理ID全部位于所用封存备份水位内，以及旧备份回退被拒绝。任何恢复不连接其他业务库或共享Watch。

## 11. 回归与交付门禁

| 验收 | 精确夹具 / 通过标准 | 当前状态 |
|---|---|---|
| DEC-D1 | WSS/REST各覆盖原创、引用自己/其他追踪/未追踪者、纯转推、回复、未知、结构冲突、作者不符；unknown后证据补全/正文补全/重放不产生新事件 | pending_protocol_review；raw映射证据另待固定 |
| DEC-D2 | 15天前1ms/等于/后1ms，未知发布时间回退、后来补旧时间只缩短、重复不续命；备份/校验/磁盘失败、备份或删除中断；清理后WSS/REST/重试/重连/重启/新代/新sub/新路径恢复均不复活；所有正文副本清除、ledger无全文、未决状态保留 | pending_protocol_review |
| DEC-C01 | published与received反序、null/未来无效时间、并列ID、多页、limit变化、错profile/filter/scope/用户cursor、更新/过期/重启/恢复；legacy默认顺序/字段不变 | pending_protocol_review |
| DEC-C03 | >一页且评分混S/A/B/C/D/null/missing，0推文订阅；全量筛选/两种计数/分页；真实本地备注；跨批变更/超时/部分结果/源停机/缓存失效；B1读写隔离和无跨库读取 | pending_protocol_review / pending_owner_implementation |
| DEC-C05 | 同代/跨代WSS/REST重复、正文/类型补全、停用恢复、进程重启，仅1稳定公开活动/1次新事件；D2清理后ledger抑制 | pending_protocol_review |
| 旧B3 | 现89个pytest（1 wrapper内Node子项不重复累加）、远端实际核验/600/异常/lease、API CRUD/commands、网站独立、DB保护；记录扩展/替代项，不能把旧成绩算新DEC通过 | 原基线证据保留，新DEC未实现 |
| 浏览器 | 1440/390真实API，备注在前；服务端SAB/查询/分页、未知回退提示、刷新/源失败/会话撤销；全生命周期共用锁，绑定构建ID/源码/截图/receipt | 既有B3进行中，认证500与刷新竞态诚实保留 |

D6/D7/D8产品已定，语音代码/播放/队列/开关仍 held，待B3/B4冻结后单独放行；本提案不生成语音PASS，不启动Mac语音任务。所有新测试仅本地合成夹具，真实6551/第三方REST/付费/Watch/公网/部署均未授权。提案提交完整SHA后由总管直接审查；批准协议不等于实现通过，C-03须双方具体SHA冻结后才实现接线。
