# 第二阶段 API 和数据规范

版本 `phase2-v1.0.0`；公开前缀 `/api/v1`，内部前缀 `/internal/v1`。此规范为各 owner 的实现与适配依据，不包含业务实现。

## 身份和 scope

固定单站点 `tenant_id="ikun-main"`。人类角色只有 `superadmin`、`user`；user 只能读业务，自己的退出/改密等认证操作仍允许。superadmin 继承 user 的业务读取权限，并可管理项目、监控和账号。服务身份是独立的方向凭据，不是第三个人类角色，不可通过服务凭据登录为用户。

Auth 在网站服务内验证 Cookie/session 的有效期、撤销、用户禁用状态、角色和强制改密。BFF 每请求校验权限，不能从 body/query/客户端 X-Role/X-Tenant 等头信任身份。客户端传入跨 scope 值拒绝；服务端固定 scope。SSE 建连、后续数据块和每15秒心跳都需重验撤销/过期，失败即关闭。业务库不得持有人类账号、密码、用户 session、角色凭据或登录限流；这些只存 auth.db。

对外 `AuthSessionV2` 为 user_id、username、tenant_id、role、must_change_password、csrf_token、capabilities。capabilities 由服务端计算，仅含 can_edit_projects、can_manage_hunter、can_manage_tracking、can_manage_users。UI 只能据此展示，不代替授权。默认能力为 false；展示模式不得伪造真实 session。

Cookie：生产 `__Host-ikun_session`，HttpOnly/Secure/SameSite=Strict/Path=/；开发仅 loopback HTTP 使用 `ikun_dev_session`。所有会话写入校验 Host/Origin/CSRF。登录不开放注册；本机隐藏输入 CLI 创建首个管理员，无默认密码。所有含密码的 HTML 表单必须显式 POST、固定同源 action，即使脚本失效也不得变成 GET 或外发凭据；fallback 可安全返回不支持表单编码。

保留的 `GET /api/auth/session` 仅是阶段兼容：返回 `{user:{id,username,role,must_change_password},csrf_token}`，不缓存、不续期，仍验证同一 auth.db session。新代码用 `/api/v1/auth/me` 的标准 envelope。reader/viewer/admin 对外统一映射 user/superadmin，不接受其为注册角色。

## ID 和项目字段

Projects 唯一生成 `prj_<小写 UUIDv4>`，永久不重用。Tracking 唯一生成 `sub_<小写 UUIDv4>`，与 project_id 分开；本阶段一个 project_id 最多一个订阅，恢复沿用 subscription_id，重新加入用 generation 区分，不重新发明项目。command 为 cmd_UUIDv4，event 为 evt_UUIDv4；correlation/receipt 是服务器生成的不透明标识，不携带账号身份。

候选 discovery_id、平台 user_id、X handle、网址、demo-* 都不是 canonical project_id。未解析发现可为 null；创建 Tracking 订阅前由项目域完成 canonical 注册并校验 scope。`(tenant_id,source,source_entity_key)` 唯一映射；平台稳定 user_id 优先，handle 变化不得导致重复项目。来源冲突进入人工核对，不能覆盖人工评分/备注或合并两个 ID。

`ProjectRecordV2` 字段冻结如下：

| 字段 | 类型与含义 |
|---|---|
| project_id | canonical ID，只读 |
| name | 非空文本，1–120 字符 |
| rating | S/A/B/C/D/null；null 显示“未评分”，不使用 unrated/待定 作为传输值 |
| description / notes | 文本，最多 4000 字符，各字段独立 |
| website_url | 安全 http/https URL 或 null；无用户名/密码，UI 不执行原始 HTML |
| category | 最多 80 字符的文本或 null，不硬编码营销分类 |
| progress_stage | todo/researching/watching/participating/completed/paused |
| progress_percent | 0–100 的有限数值或 null；未知不能虚构为 0/100 |
| token_date | YYYY-MM-DD 或 null；这是日期，不能当 UTC 时间戳 |
| token_date_status | confirmed/estimated/unconfirmed；null 日期须 unconfirmed，有日期须 confirmed/estimated |
| home_membership | hidden/active/removed；主页默认查询 active |
| discovered_at | 已知发现 UTC ISO8601 时间或 null；仅有日历日的演示数据不可伪造精确时间 |
| revision | 服务端递增整数，起始 1 |
| created_at / updated_at | 服务端 UTC ISO8601 时间，只读 |

显示层可转换北京时间；传输为 snake_case、UTC ISO8601，金额/链上大整数保留十进制字符串。评分等级与进度独立，不能由 UI 擅自推算。

加入监控与加入主页是两个显式动作。仅人工确认监控的项目可注册为 hidden，不自动出现在 active 主页。新增主页或明确恢复才成为 active；主页 DELETE 只变 removed，并保留 canonical ID、来源、审计和监控引用。**不自动暂停、删除或修改 Hunter/Tracking。** 删除/移除订阅也不修改主页项目。重复来源导入不得自动复活 removed。

## 通用响应和写入

成功 `{data,request_id}`；分页 data 为 `{items,next_cursor}`，默认 limit=50、最大100；opaque cursor，不用于监控 checkpoint。错误 `{error:{code,message,retryable},request_id}`，每响应 X-Request-ID/no-store。客户端 request ID 只允许 1–64 字符字母数字下划线横杠。

所有业务与账号管理写入需 UUID Idempotency-Key，principal/scope/route 作用域，至少保留7天；同 key/同规范化 body 返回原结果，异 body 409 IDEMPOTENCY_CONFLICT。PATCH/DELETE/恢复与状态操作需 If-Match `"rev-N"`，响应 ETag 同格式；缺失428、过期409 VERSION_CONFLICT。同步创建201，同步变更/主页移除200，监控确认及订阅创建/运行/移除等异步命令202。202/ACK只表示持久受理，不表示远端已执行。

登录、退出、本人改密是会话轮换例外，不缓存/回放原始 token；退出幂等。500/unknown/写请求超时先查原操作回执，不能自动重复资金、付费或平台写入。退避/Retry-After 由业务层控制，公共 UI 不做副作用重试。

错误 code 使用共享 ErrorCode：400/422 VALIDATION_ERROR，401 UNAUTHENTICATED，403 FORBIDDEN，404 NOT_FOUND，409 CONFLICT/IDEMPOTENCY_CONFLICT/VERSION_CONFLICT，428 VALIDATION_ERROR，429 RATE_LIMITED，502/504 UPSTREAM_UNAVAILABLE/UPSTREAM_TIMEOUT，503 DB_UNAVAILABLE/AUTH_NOT_CONFIGURED，501 NOT_IMPLEMENTED，500 INTERNAL_ERROR。retryable 仅限可核实的临时错误；凭据/未实现/版本冲突不重试。

## 公开 API 所有权

| 方法和路径 | owner | 权限和输入 |
|---|---|---|
| POST /auth/login、/auth/logout、/auth/password | auth | 会话与安全轮换协议 |
| GET /auth/me | auth | 本人真实会话 |
| GET/POST /auth/users | auth | superadmin；创建 role 只能两种 |
| PATCH /auth/users/{user_id} | auth | superadmin、enabled、revision |
| POST /auth/users/{user_id}/reset-password | auth | superadmin、revision、隐藏密码 |
| GET /projects | projects | user；q/rating/progress_stage/home_membership/cursor/limit |
| POST /projects | projects | superadmin；ProjectFieldsV2，明确加入主页 |
| GET/PATCH/DELETE /projects/{project_id} | projects | 读 user，写 superadmin；删除只移除主页 |
| POST /projects/{project_id}/home-membership | projects | superadmin；action add/remove、If-Match；显式恢复 |
| GET /hunter/signals、/hunter/discoveries/{discovery_id} | hunter BFF | user；脱敏聚合 DTO |
| GET/POST /hunter/accounts | hunter BFF | superadmin；仅本 v2 管理 |
| PATCH/DELETE /hunter/accounts/{account_id} | hunter BFF | superadmin、revision；不得改共享 Watch |
| POST /hunter/discoveries/{discovery_id}/monitoring-requests | hunter BFF | superadmin、confirmed=true、revision；202 返回 CommandResultV2 |
| GET/POST /tracking/subscriptions | tracking BFF | 读 user，写 superadmin；canonical project_id、confirmed=true |
| GET/PATCH/DELETE /tracking/subscriptions/{subscription_id} | tracking BFF | 读 user，写 superadmin；删除异步返回命令 |
| POST /tracking/subscriptions/{subscription_id}/{operation} | tracking BFF | superadmin；operation start/stop/resume，revision |
| GET /tracking/latest、/tracking/activities | tracking BFF | user；脱敏、cursor/limit |
| GET /commands/{command_id} | projects gateway | user；当前 scope 的命令视图 |
| GET /events/stream | website gateway | user；脱敏 SSE、15秒心跳、Last-Event-ID 重放，重放不重复告警 |

表内路径统一补 `/api/v1`。请求与投影 DTO 见 DTO.md，TypeScript 传输声明见 packages/contracts/src/phase2.ts。旧 /api/home、/api/hunterradar/v1、/api/tracking 只能是明确关闭/受限的候选适配层，不成为新的对外协议，不带独立用户登录。

## 内部传递和恢复

网站→Hunter 使用 HUNTER_API_TOKEN；网站→Tracking 使用 TRACKING_API_TOKEN；Hunter/Tracking→项目接收分别使用 PROJECTS_INGEST_HUNTER_TOKEN / PROJECTS_INGEST_TRACKING_TOKEN。各方向至少32字符随机值，独立 scope，不复用用户 session 或 provider key。方向凭据只由服务器持有。

worker `POST /internal/v1/commands`、`GET /internal/v1/commands/{command_id}`、`GET /internal/v1/events`、`GET /internal/v1/subscriptions` 是服务接口。人类命令携带 BFF 刚验证的 AuthPrincipalV2；worker 验证调用方向、固定 scope、operation allowlist 和 actor role。原始浏览器头不能穿透为受信身份。

网站 `POST /internal/v1/ingest/{source}` 接收 EventEnvelopeV2；`GET /internal/v1/receipts/{source}/{event_id}` 用对应来源凭据 reconcile。EventReceiptV2 包含 event_id/project_id/receipt_id/accepted_at/duplicate/command_id；它是受理回执，不是监控已运行。

人工监控 event_type 固定 `hunter.monitoring_requested`，payload 为 MonitoringRequestPayloadV2（command_id、confirmed=true、actor、候选项目字段、X稳定ID/handle）。Hunter 为该幂等操作生成并持久化唯一command_id，在自身 DB 原子保存确认、revision、outbox后发送；项目域在 projects.db 原子校验/映射 canonical（必要时 hidden）、写 inbox receipt 与沿用同command_id的Tracking command outbox；网站再投递 Tracking commands，Tracking 在自己库保存 inbox/订阅/命令状态后ACK。每个发送方收到回执再标记本地完成，任何跨库步骤都不是分布式事务。

尚未完成canonical映射时，人工确认的CommandResultV2允许project_id/subscription_id=null并显示pending；gateway按来源凭据查询Hunter已有命令投影，取得项目回执后查询Tracking实际状态。command_id不能改变，不因网站/Projects暂不可用重新确认。直接创建Tracking订阅仍要求非null canonical project_id；CommandEnvelopeV2投递前也必须解析完整canonical引用。

观察事件只保存最小脱敏资料，不等同人工确认。事件 source/schema/version/hash 校验，重复同 hash 幂等、异 hash 冲突。occurred_at 可未知；received_at 由拥有原始观察的 worker 写入；网站另写 accepted_at，不能用客户端时间替换服务端受理时钟。72小时窗口与 generation/baseline 在 Hunter 域计算。

CommandEnvelopeV2 按固定 operation 与 canonical 引用执行，unknown 先查远端/回执再决定补投。SubscriptionRecordV2 分离 desired_state、observed_state、operation_state、connection。running 必须由远端真实状态确认，connected 必须有有效来源心跳；ready、SSE在线、ACK、进程存在均不代替这些证据。普通用户 DTO 不含 Hunter 个体身份、账号列表、raw payload、token、Cookie 或私有 provider URL。superadmin 专用账号管理 DTO 仅例外显示所管理的账号 ID/handle，仍不得暴露其凭据或归因明细。
