# API 契约 v1 · 开发窗口共同基线

本文件定义将来实现的接口；当前已运行的仅 health 和 worker status。业务接口没有模拟成功响应。更改契约需总管审阅，同步 `packages/contracts`、本文件和测试；不允许窗口自行改字段名。

## 通用约定

JSON UTF-8、snake_case、UTC ISO 8601（显示层可换时区）；金额/大整数为十进制字符串，禁止浮点保存金额。项目 ID 格式在 contracts 中校验。所有公共 API 前缀 `/api/v1`，内部前缀 `/internal/v1`；除明确公开元信息以外均需鉴权。内部服务只监听 loopback，浏览器只能调用网站同源 API。

成功：`{"data":{},"request_id":"..."}`；分页 data 为 `{"items":[],"next_cursor":null}`。错误：`{"error":{"code":"...","message":"...","retryable":false},"request_id":"..."}`。每响应带 X-Request-ID；客户端传入 ID 最长 64，只允许字母/数字/下划线/横杠；不得记录请求体或 secrets。分页 limit 默认 50、最大 100，opaque cursor，排序 `(updated_at, id)`；不能将页码当 checkpoint。

写入必须 `Idempotency-Key`（UUID、作用域 principal/route，至少保留 7 天）；接收方保存规范化 body hash，重复键同 body 返回原结果，不同 body 返回 409 IDEMPOTENCY_CONFLICT。PATCH/DELETE 必须 If-Match 对应 revision ETag（如 `"rev-3"`），缺失 428、过期 409 VERSION_CONFLICT。创建 201、异步命令 202、查询/变更/逻辑删除 200；逻辑删除返回 tombstone 与新 revision。重试失败前查询 command/receipt 状态。

## 已实现接口

| 服务 | 方法/路径 | 权限 | 含义 |
|---|---|---|---|
| 三服务 | GET /health/live | loopback | 进程存活，200 |
| 三服务 | GET /health/ready | loopback | 自己的存储可读，200/503 |
| 两 worker | GET /internal/v1/status | 本服务 bearer token | idle、external_io_enabled=false |
| 网站 | /api/v1/* | 业务关闭 | 503 AUTH_NOT_CONFIGURED |
| 网站 | /internal/v1/ingest/hunter、tracking | 对应方向 token | 未配置 503，错误 token 401，通过后 501 |
| 两 worker | /internal/v1/*（除 status） | 本服务 token | 未配置 503，错误 token 401，通过后 501 |

health 不提供 DB 路径、配置、账号、数据量或 secrets。ready 不验证真实登录、外部数据源和业务交付。GET/POST/PATCH/DELETE 只是 skeleton gate，不代表 CRUD 已开发。

## 目标公共 API（全部待分配业务窗口实现）

| 方法/路径 | 所有者 | 最低权限 | 输入/返回要点 |
|---|---|---|---|
| POST /api/v1/auth/login | auth | 匿名 + 限流 | 凭据 → session cookie，不回传密码/hash |
| POST /api/v1/auth/logout | auth | session | 撤销 session，幂等 |
| GET /api/v1/auth/me | auth | session | user_id、tenant_id、role |
| POST /api/v1/auth/users | auth | superadmin | 创建用户，不允许公开注册 |
| PATCH /api/v1/auth/users/{user_id} | auth | superadmin | 禁用用户、撤销会话 |
| POST /api/v1/auth/users/{user_id}/reset-password | auth | superadmin | 安全重置、会话撤销、审计 |
| GET /api/v1/projects | projects | user | tenant 约束、cursor、limit、status |
| POST /api/v1/projects | projects | superadmin | name、source refs → ProjectSummary、ETag |
| GET /api/v1/projects/{project_id} | projects | user | 脱敏项目 DTO；跨租户统一 404 |
| PATCH /api/v1/projects/{project_id} | projects | superadmin | 允许字段 patch + If-Match；禁止改 ID/tenant |
| DELETE /api/v1/projects/{project_id} | projects | superadmin | archive tombstone；保留审计/事件引用 |
| GET /api/v1/hunter/signals | hunter BFF | user | 仅聚合信号、project_id、时间、count；不含猎手身份 |
| GET/POST /api/v1/hunter/accounts | hunter BFF | superadmin | 本 v2 管理；绝不复用/改共享 Watch |
| PATCH/DELETE /api/v1/hunter/accounts/{id} | hunter BFF | superadmin | 本地 pause/tombstone、revision；未来平台更改需授权 |
| GET/POST /api/v1/tracking/subscriptions | tracking BFF | user/superadmin | 当前 tenant、project_id、订阅配置 |
| PATCH/DELETE /api/v1/tracking/subscriptions/{id} | tracking BFF | superadmin | revision、暂停或 tombstone，不物理删除历史 |
| GET /api/v1/commands/{command_id} | projects | user | 当前 tenant 的 persisted command 状态 |
| GET /api/v1/events/stream | projects | user | 脱敏 SSE、15 秒心跳、Last-Event-ID 重放、不重复提醒 |

不做全局用户资源列表。未认证 401，无权限 403，资源跨租户不可枚举返回 404。query/body 不得决定 user_id/role；tenant 来源于 session，超级管理员切换 tenant 必须显式授权。

## 目标内部 API（全部待实现，除 status）

| 服务/方法/路径 | 调用方/凭据 | 约定 |
|---|---|---|
| 网站 POST /internal/v1/ingest/hunter | hunter → PROJECTS_INGEST_HUNTER_TOKEN | 单个脱敏 EventEnvelope，durable receipt |
| 网站 POST /internal/v1/ingest/tracking | tracking → PROJECTS_INGEST_TRACKING_TOKEN | 同上，拒绝 source 与凭据不匹配 |
| 网站 GET /internal/v1/receipts/{source}/{event_id} | 对应来源 token | reconcile，不含别的来源记录 |
| worker GET /internal/v1/events | 网站 → HUNTER_API_TOKEN 或 TRACKING_API_TOKEN | 授权 tenant/source filter、cursor replay |
| worker POST /internal/v1/commands | 网站 → 对应 worker token | command_id、tenant_id、actor、operation、target_id、revision、payload |
| worker GET /internal/v1/commands/{command_id} | 网站 → 对应 worker token | durable task state；ACK≠业务完成 |

每个方向至少 32 字符随机 token，独立生成与轮换，不复用认证 session 或第三方 API key。范围只允许本方向和分配 tenant；v1 将由总管审核 tenant allowlist 配置后启用，当前业务路径始终关闭。签名/重放保护的加强方案需另行版本化，静态 token 不宣称来源不可伪造。

事件示例（示意契约，无真实业务数据）：

```json
{
  "schema_version": 1,
  "event_id": "evt_550e8400-e29b-41d4-a716-446655440000",
  "source": "hunter",
  "event_type": "project.signal_observed",
  "occurred_at": "2026-10-15T00:00:00.000Z",
  "received_at": "2026-10-15T00:00:01.000Z",
  "tenant_id": "ten_550e8400-e29b-41d4-a716-446655440001",
  "project_id": null,
  "correlation_id": "cor_550e8400-e29b-41d4-a716-446655440002",
  "payload": {"source_entity_key":"example_candidate","display_name":"Example","aggregate_count":2}
}
```

receiving ACK 的 data 必含 event_id、project_id（解析后的 canonical）、receipt_id、accepted_at、duplicate；同一 event_id 同 hash 幂等，异 hash 冲突。schema_version 不认识则拒绝。received_at 由接收节点独立记录，不能用客户端时间代替服务端去重/窗口时间。

## 权限矩阵

仅 superadmin/user 两种角色，普通用户只能查看，不允许修改业务数据；不开放公开注册。首次超级管理员通过本机安全 CLI 创建，不在 Git/日志中保存初始密码。CLI 与权限执行由认证窗口实现。tenant_id 初始为服务端固定单站点 scope，保留未来隔离契约，不要求本阶段实现组织管理。

| 操作 | user | superadmin | worker |
|---|---|---|---|---|
| 当前 scope 脱敏项目/跟踪读 | 是 | 是 | 只限约定接口 |
| 当前 scope 项目/跟踪/监控写 | 否 | 是 | 不直接写 projects.db |
| 项目归档/猎手配置/用户管理 | 否 | 是 | 无用户权限 |
| 原始猎手身份进入公共 DTO | 否 | 否 | 禁止导出 |
| 接收本来源事件/命令 | 否 | 经 BFF | 仅 token scope |

## 错误表与恢复

| HTTP | code | retryable | 处理 |
|---|---|---|---|
| 400/422 | VALIDATION_ERROR | false | 修改参数 |
| 401 | UNAUTHENTICATED | false | 重新认证，不自动反复提交凭据 |
| 403 | FORBIDDEN | false | 人工权限处理 |
| 404 | NOT_FOUND | false | 资源缺失/不可见 |
| 409 | CONFLICT / IDEMPOTENCY_CONFLICT / VERSION_CONFLICT | false | 读取最新状态/人工处理 |
| 428 | VALIDATION_ERROR | false | 补 If-Match |
| 429 | RATE_LIMITED | true | Retry-After，保留任务 |
| 502/504 | UPSTREAM_UNAVAILABLE / UPSTREAM_TIMEOUT | true | 有界退避，写入先 reconcile |
| 503 | DB_UNAVAILABLE | true | 暂停本域写入，保留 checkpoint |
| 503 | AUTH_NOT_CONFIGURED | false | 模块/凭据未配置，禁止空凭据回退 |
| 501 | NOT_IMPLEMENTED | false | 待开发；不能伪造空成功 |
| 500 | INTERNAL_ERROR | false | 记录 request_id，人工调查/确认是否已提交 |

未知/资金/付费任务不得盲目重试；SSE 重连补历史只更新 UI，不重新语音/推送。删除项目先 archive，再通过持久命令暂停引用订阅；跨库清理由 saga/补偿任务完成。认证账号删除先撤销 sessions 再审计，不 cascade 物理删除业务记录。
