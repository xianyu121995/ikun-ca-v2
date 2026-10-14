# ikun.ca 主页项目领域候选

只访问独立 `projects.db`。包含真实项目 CRUD、S/A/B/未评分、简介/官网/备注/研究进度/发币日期、搜索/排序/筛选/分页、明确加入 API、稳定 ID、角色及租户校验、审计、版本冲突、导入回执。没有采集器、WSS、REST 轮询或 NEW_TWEET 任务。

当前为隔离候选。主页沿用旧版已确认的三段布局和八列表格；未覆盖其他窗口的新 UI 原型，未修改主网站/认证/worker/共享 contracts，未部署。共享集成差异见 [INTEGRATION.md](docs/INTEGRATION.md)。

## 启动

在本 `candidate` 目录执行（Python 3.11+）：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m projects_service migrate
.venv/bin/python -m projects_service create-client --role superadmin --out secrets/local-superadmin.json
.venv/bin/python -m projects_service serve
```

在本机创建 `data/projects.db` 及 `secrets/local-superadmin.json`；凭证文件已存在时跳过 create-client 命令。访问 `http://127.0.0.1:8120`，在本机打开凭证文件，将 `token` 填入登录框；不要发到聊天。文件为 0600，并被 Git 忽略，凭证不会出现在命令输出。数据库初始没有项目；界面不注入演示数据。

改变端口时同时设置同源地址，例如：

```sh
PROJECTS_ORIGIN=http://127.0.0.1:8121 .venv/bin/python -m projects_service serve --port 8121
```

公网配置必须使用单一 HTTPS 来源，设置 `PROJECTS_SECURE_COOKIE=1`，通过既有反向代理保护入口。默认仅监听 loopback，单 worker；限流为单进程内存状态（重启清零），业务幂等/会话/审计持久化。当前凭证登录仅用于独立候选；正式账号集成不能用该凭证替代 auth 模块。

## API

所有业务路由需要本服务验证的 Bearer 凭证，或登录获得的 HttpOnly/SameSite Cookie。Cookie 写请求另需同源 Origin 和 X-CSRF-Token。不能通过 X-Role/X-User-Id/X-Tenant-Id 指定身份。查询只返回当前凭证绑定租户的数据，跨租户项目统一 404。

| 方法 | 路径 | 角色/用途 |
|---|---|---|
| POST / GET / DELETE | `/api/home/session` | 登录 / 权限 / 退出 |
| GET | `/api/home/projects`（别名 `/api/home/tracking`） | user/superadmin；q/rating/progress/sort/limit/offset |
| GET | `/api/home/projects/{id}` | 当前租户项目 |
| POST | `/api/home/projects` | superadmin；必须 Idempotency-Key |
| PATCH | `/api/home/projects/{id}` | superadmin；body 必须 expected_version |
| DELETE | `/api/home/projects/{id}?expected_version=N` | superadmin；逻辑删除，仅本库 |
| GET | `/api/home/important-times` | 已加入项目的未来发币日期；limit/offset，上海日期边界 |
| POST | `/api/home/imports` | 仅服务身份，凭证绑定 source 与 tenant |
| GET | `/api/home/import-receipts?source=...&external_id=...` | 服务身份只查询本来源的持久回执 |
| GET | `/healthz` | 存储可读检查，不代表监控连接 |

`sort`：updated / discovered_desc / discovered_asc / rating / token_date / name。`limit` 默认 20，最大 100；`offset` 为普通页面分页，不作为采集 checkpoint。q 在项目名称/简介/官网/备注搜索，LIKE 特殊符号视作字面文本。评分、进度、排序字段白名单校验。

请求/响应字段见自动生成的 `/openapi.json`。错误包含稳定 `error.code`、`error.message`、`error.retryable`、`request_id`；响应带 X-Request-ID。400/401/403/404/409/410/422 不自动重试；429/503 提供 Retry-After。浏览器请求超时 12 秒，保留表单及新增幂等键以便人工重试。

## 受控加入与重复导入

本机创建方向独立的凭证（不会输出 token）：

```sh
.venv/bin/python -m projects_service create-client --source hunter --tenant default --out secrets/hunter-import.json
.venv/bin/python -m projects_service create-client --source tracking --tenant default --out secrets/tracking-import.json
```

API 资料格式：

```json
{
  "source": "hunter",
  "external_id": "stable-provider-project-id",
  "explicit_add": true,
  "project": {
    "name": "用户明确加入的项目",
    "rating": "unrated",
    "description": "脱敏后的项目简介",
    "website": "https://example.org",
    "notes": "",
    "progress": "todo"
  }
}
```

可带 `project_id: "prj_<UUID v4>"` 指向当前租户已有项目；不会覆盖人工字段。一个来源记录不能改绑到另一个项目，冲突返回 409。未指定 ID 时以 `(tenant, source, external_id)` 去重；相同规范化官网可关联跨来源记录。无共同 ID/官网的不同来源资料不会凭名称猜测合并，需要显式指定已有 project_id。

官网身份忽略 scheme、www、query/fragment、默认端口和末尾斜杠，保留路径；同域名的不同路径可以代表不同项目。只校验地址，不抓取官网。额外字段直接拒绝，不接收 Hunter 身份、raw payload 或账号列表。

删除保留本库 tombstone、来源映射和审计，不发跨模块删除命令。重复导入已删除项目返回 410，回执查询仍返回稳定 ID 和 deleted=true。创建与导入分别使用持久回执，写入与审计在同一 SQLite 事务提交；并发导入不会产生重复记录。导入重复资料不刷新人工评分/备注/进度。

## 角色和凭证管理

用户角色只有 superadmin/user：user 只读，superadmin 可新增/修改/删除。独立服务身份没有用户角色，只能调用本来源加入/回执 API，不能登录主页或操作普通 CRUD。所有凭证绑定固定租户，默认 default。新凭证用 `create-client --tenant <tenant>` 指定，禁止通过请求自行切换。

```sh
.venv/bin/python -m projects_service revoke-client <principal_id>
```

撤销后现有会话立即失效。token 及 session 只在 projects.db 存 SHA-256；不记录请求体/凭证，校验错误不回显输入。Cookie 会话 8 小时过期；浏览器仅保存 CSRF 值于 sessionStorage。新标签页无 CSRF 值时重新登录。

## 迁移、备份和测试

迁移 001 创建主数据/来源/凭证/会话/幂等/审计；002 创建租户查询索引。迁移脚本校验和持久化，重复执行安全，校验和漂移拒绝启动。使用 WAL、foreign_keys、同步提交和 3 秒 busy timeout；锁忙返回 503，不删除或重建库。只接受名称 projects.db 和本 V2 application_id，拒绝其他已有库、符号链接和硬链接。

迁移只在 CLI 或服务启动阶段运行，不在业务请求里运行。回滚使用**本库的完整 SQLite 备份**，不提供破坏性 down；不要只复制运行中的 .db 而忽略 WAL。需要备份时用 SQLite backup API，并停止主页写入后做恢复。

```sh
.venv/bin/python -m pytest -q tests/test_projects.py
.venv/bin/python -m pytest -q tests/test_browser.py
node --check projects_service/static/home.js
node --check integration/next-proxy.js
```

浏览器测试需要本机 Chromium；自动选取已安装 Playwright Chromium，也可设置 PROJECTS_TEST_CHROMIUM 为可执行文件路径。所有测试使用临时 projects.db 和随机 loopback 端口，不接入真实 worker。截图 [homepage-fixture-1440.png](docs/homepage-fixture-1440.png) 为隔离测试数据。

临时 Next.js 同源接入的独立复现命令及公共 Origin/内部 Host 配置见 [INTEGRATION.md](docs/INTEGRATION.md)。此验收未改动正式 apps/website。
