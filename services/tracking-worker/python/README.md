# ikun.ca 独立项目 NEW_TWEET 引擎

本模块在 `codex/tracking-worker`，只写自己的 `tracking.db` 及其 SQLite WAL/SHM。没有 hunter/projects/auth 数据库路径、跨库 SQL、旧版账号导入或共享 Watch 修改。默认关闭真实远端调用。`serve` 将业务 API 与引擎放在同一个 tracking 服务进程，网站独立运行；没有新增正式服务。

## 运行

Python 3.11+。在本目录：

```sh
uv venv --python python3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
uv pip install --python .venv/bin/python --no-deps -e .
cp config.example.json config.local.json
.venv/bin/python -m tracking.cli init --config config.local.json
.venv/bin/python -m tracking.cli serve --config config.local.json
```

本地页面 `/tracking`。独立测试模式使用 `IKUN_TRACKING_ADMIN_TOKEN` / `IKUN_TRACKING_READ_TOKEN` 两个不同的至少 32 字符随机值，或配置 0600 的凭证文件；不在聊天填写。页面只存 HttpOnly session，凭证不进 localStorage、HTML、日志。

正式主站接入使用 `auth_session_url` 指向认证服务的 loopback `/api/auth/session`、`auth_origin` 为网站真实 Origin、`auth_cookie_name` 为其 session cookie。每次业务请求通过认证 API 检查用户、撤销、强制改密；superadmin 可写、user 只读。写请求验证主站 Origin 和 CSRF。此模式禁止独立 tracking 登录，不读取 auth.db。

Node 正式入口保持原基础模式；明确设置 `IKUN_TRACKING_CONFIG` 为绝对路径时，`pnpm start:tracking` 启动本实现。`IKUN_TRACKING_PYTHON` 可指定绝对 Python 路径。开发 Worktree 使用自己的 3412 端口和数据目录；生产配置另行审核，默认示例的 3112 不应与其他 Worktree 共用。

## API

正式接入候选为 `/api/v1/tracking`，所有成功/失败带 request_id，写入 UUID Idempotency-Key，变更使用 `If-Match: "rev-N"`；ID 必须为项目领域提供的 `prj_<UUIDv4>`。时间返回 UTC ISO 8601。创建表示本地确认已持久化，监控启用须查看远端核验状态。

| 方法 / 路径 | 用途 |
|---|---|
| GET /subscriptions | 分页查询，limit≤100，opaque cursor |
| POST /subscriptions | 超级管理员人工确认项目与账号后加入；201、远端仍待确认 |
| GET /subscriptions/{project_id} | 详情、ETag、远端状态、累计条数及最新推文时间 |
| PATCH /subscriptions/{project_id} | 编辑名称/备注；账号与项目 ID 不可静默替换 |
| POST /subscriptions/{project_id}/start、stop、resume | 持久化异步命令；202 |
| DELETE /subscriptions/{project_id} | 请求远端移除；202，保留历史，核验前不隐藏失败项 |
| GET /status | 独立进程与真实来源心跳状态 |
| GET /latest | 最新入库动态，可按 project_id 查询 |
| GET /activities | seq cursor 增量读取，不重复消费 |

`/api/tracking/*` 是独立页面适配接口：操作使用 body.expected_revision；不作为共享 v1 契约的替代。`/health/live`、`/health/ready` 仅检查进程/本库，不证明远端采集成功。

## 远端状态与恢复

- 请求状态 desired、远端查询结果 remote_state、WSS 连接状态分别保存。订阅 ACK 与有效 pong、worker 心跳和 Watch 回查均有效时，页面才显示“正在接收”。过期结果显示 unknown/recovering。
- 启停/移除调用后重新查询完整 Watch；超时也先回查。成功 ACK 但实际未改变，进入重试。停止通过删除本模块拥有的远端条目释放名额，恢复重新添加。
- 写入前持久化 ownership reservation；仅操作本模块已声明且 groupName 精确匹配的账号。发现旧配置、未知分组、缺字段、分页不完整、外部事件开关变化均阻止覆盖。不会为了腾名额删除其他账号。
- 名额不足、429、5xx、断线持久化重试时间，指数退避和抖动，尊重 Retry-After。外部 HTTP 串行限速，WSS 有界消息大小/队列、ACK/pong 超时和重连。
- SQLite 单 worker 租约、revision 检查和原子去重；崩溃后由独立 supervisor 恢复，30 秒租约失效后接管。正常 SIGTERM 协调 API/引擎退出并释放租约。暂停/重新加入产生新 generation，旧推文不能伪装为新动态。
- 本地严格筛选 NEW_TWEET、作者和发布时间，排除 reply/quote/retweet。`handle+tweet_id` 唯一，空正文后续补全不产生第二条动态。
- 初次、重连后及周期性 REST 恢复采集最多最近 100 条。超过窗口显示 possible_gap，失败显示 recovery_failed；不承诺任意长断线都能补齐历史。服务端没有已验证的无限分页/重放协议。

真实远端启用同时要求 `remote_enabled=true`、`dedicated_account=true` 和独立凭证。独立分组不能隔离同一个 6551 账号的配额/权限；正式环境必须使用独立账号。6551 没有条件更新/CAS 的已验证契约，不能对同一账号的其他人工写入提供原子隔离保证。当前没有借用旧版 Token，也没有发起真实 Watch 增删。

## 页面与集成边界

`static/` 是已接真实本地 API 的运行页面；`integration/next/` 是网站 owner 可审阅的同源 BFF 候选，`deploy/nginx-tracking.conf` 为另一种路由方式，二选一。均未安装或部署。

`integration/monitor-adapter.mjs` 对接 tracking-ui 的 presentation contract，真实接口驱动 start/stop/resume/remove，不使用模拟状态定时器。当前 UI 原型只接受 mode=demo、缺 canonical project_id、包含模拟/已读/分类/操作日志控件；正式切换必须由 UI owner 接受 mode=live、传入人工确认项目回调并关闭不支持的控件。分类、已读与面板日志没有虚构数据；分类显示“未分类”。累计推文数量来自本库真实 COUNT。

主站原型/BFF 文件归其他窗口，本次只交付本模块内的接入候选，不改其文件。生产接通需总管完成接口审阅、正式 UI/认证组合验收和批准部署。详见 HANDOFF.md；不把候选测试等同已上线。

## 测试

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check tracking tests --select E4,E7,E9,F,I,UP
node scripts/browser-smoke.mjs
node scripts/bff-smoke.mjs
node scripts/adapter-smoke.mjs
node scripts/launcher-smoke.mjs
```

浏览器脚本需要 Playwright（PLAYWRIGHT_MODULE 可指定）和 Chrome（CHROMIUM_EXECUTABLE 可指定），仅启动临时本机服务，远端关闭。所有 vendor 用例均为 MockTransport 或 loopback 模拟，不消耗真实 6551 名额。
