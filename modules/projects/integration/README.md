# B2 本地接线候选

这里只保存 Projects 自有接线。定稿 UI、Auth、B0 和根网站均从固定 Git 对象导出到忽略的 `modules/projects/.preview`；未修改其他 Worktree、正式网站路由、共享依赖/锁或运行服务。正式收件、真实 worker 联调、公网验收和部署仍未放行。

规范为 `phase2-v1.0.0 + auth-b1-final-v2 + projects-home-v1`。批准来源：B2 `4b2e33b0d4996c93d6df9bd5ef265fe0d2ddcaf5`、主页补充 `6595c4a05b736889a4649b1d0aa7405601deebc4`、集合补充 `379c6e583e487f038629e1ca24d4b2614970ad0c`。依赖完整 SHA 记在 build-inputs/报告。

## 数据与入口

Python 仅开 projects.db，沿用 `candidate/projects_service/db.py` 的创建、修改、来源解析、成员移除和审计。SQL 唯一来源 `schemas/projects`；foundation1 字节不变，业务2。显式迁移、0700/0600、别名拒绝、错库/未来版本/checksum 拒绝。旧候选有人类凭证时保留原库并拒绝升级，交 owner 审查退役；不复制旧登录到新版。

HTTP-over-UDS 使用 B0 `ManagedProjectsIpc`：私有短路径 socket、随机方向凭据、build_sha/入口 hash、受控生命周期。Python 无正式 TCP 入口，不读取 Auth/Hunter/Tracking 数据库。网站启动候选先验证精确 B1 schema，再托管 IPC 和 Next；不自动迁移或启动采集。

实际 Route Handler 运行 B1 `withAuth`、`requireIdentity/requireSuperadmin`；页面运行 `requireAuthPage`，Server Action 运行 `requireSuperadminAction`。只将刚验证的安全 principal 传给 Python。候选把 home-summary、milestones、UUID 操作回执列为精确只读白名单，复用同一个 B1 AuthStore/AuthHttp；Proxy 和 handler 分别初始化同一策略，不信任客户端角色头。SSE 由 B1 包装，静默每秒检查撤销，并发数据块同样检查；提供15秒心跳。

## API

所有响应使用标准 envelope/request_id/no-store。项目写入 UUID Idempotency-Key 至少保存7天；条件更新用 If-Match/ETag。DELETE 只设置 removed，保留 ID、进度、来源和引用。

| 路径 | 行为 |
| --- | --- |
| GET/POST `/api/v1/projects` | phase2 默认投影/创建；`view=home-v1` 为复合投影/事务 |
| GET/PATCH/DELETE `/api/v1/projects/{id}` | 查询、编辑、仅从主页移除 |
| POST `/{id}/home-membership` | add/remove，只改成员状态 |
| POST `/{id}/completion`、`/completions`、`/{id}/restore` | 完成、1–100项全成全回滚、真实快照恢复 |
| GET `/api/v1/projects/home-summary` | 独立真实计数，可按发现日期计 tracked/by_rating |
| GET `/api/v1/projects/milestones` | 独立 active S/A/B 事件、北京时间窗口、真实 cursor |
| GET `/api/v1/projects/operations/{key}` | 当前 actor/scope/method/path/contract 的原操作回执 |
| GET `/api/v1/commands/{id}` | 本域 outbox/真实远端回执的脱敏状态，不猜运行成功 |
| GET `/api/v1/events/stream` | 项目变化重放/心跳，B1 撤销控制 |
| POST `/internal/v1/ingest/hunter` | 独立方向凭据；仅人工 confirmed 监控事件 |
| GET `/internal/v1/receipts/{source}/{event_id}` | 对应来源凭据的持久回执 |

表内 `/{id}` 路径均在 `/api/v1/projects` 下。Tracking 观察接收当前明确返回 NOT_IMPLEMENTED；不启动冻结 worker。来源冲突返回409，不覆盖手工字段。Hunter confirmed 事件在一个 projects.db 事务内写 canonical、inbox receipt 和同 command_id 的 Tracking outbox。`outbox-relay.ts` 仅提供网站 owner 可调的单次投递函数；没有自动后台轮询/平台调用。unknown 总是 GET 原远端 command 后再决定，真实 Tracking 未联调。

home-v1 列表接受 collection=tracked/completed/other、q/rating/progress_stage/home_membership/discovered_on/sort/direction/limit/cursor。collection 缺省仍 active；显式 membership 与集合取交集。默认 discovered/desc，未知值总在末尾，ID升序打破同值；名称为 SQLite BINARY Unicode 排序。progress 按冻结枚举、百分比排序，event 按独立日期/小时排序。所有条件在数据库 LIMIT 前执行，total 同一读取快照；cursor 绑定全部规范化条件、显式 membership 状态、集合、limit、scope 与 profile。

## 定稿页面候选

`patches/homepage-server.patch` 只在固定 Git 导出的忽略预览中应用，改两个 UI 文件的输入/回调接线；原 UI 分支不变，CSS/文案/导航不改。server 模式直接使用服务器有序页/total/summary 和独立事件、完成、其他集合，不执行本地查询排序/slice。弹窗使用既有按钮样式提供必要的独立分页；这部分也是待总管收件的显式补丁。

补丁为零上下文 unified diff，避免空白上下文行被提交白空格检查误报；仅在先核对定稿源码 SHA 后用 `git apply --unidiff-zero` 应用。构建器自身用严格固定源码上下文生成相同结果，记录补丁 hash。

查询、排序、日期和翻页清选择/cursor，过期请求取消并有 epoch 检查。独立集合选择最新 revision，避免异步旧页覆盖新记录。写入超时保留原 key；回执404仍 unknown，不自动重新 POST。待核对元数据只在当前账号 sessionStorage 保存 method/path/contract/key，不存请求原文或凭据。

## 本地构建和测试

在 Projects Worktree 根目录，先准备 Node24.22+/pnpm10.33 和 candidate 的 Python3.11+ venv（依赖见 pyproject.toml）：

```sh
python3 -m venv modules/projects/candidate/.venv
modules/projects/candidate/.venv/bin/python -m pip install -e 'modules/projects/candidate[test]'
B2_NODE=/absolute/node24 python3 modules/projects/integration/build-preview.py
cd modules/projects/candidate
.venv/bin/python -m pytest -q tests --basetemp=/private/tmp/ikun-b2-regression
```

构建串行运行 contracts/runtime/UI/Auth/Next，产出 `artifacts/build.log` 与完整源码 hash receipt。浏览器测试需 Chromium，使用本机 Playwright 缓存；仓库当前测试定位 macOS Node/Chromium，换平台需设置相应路径再验收。fixture 只用临时库/合成账号，本机随机端口，结束关闭进程。

## 启动隔离预览

复制 `.env.example` 为忽略的 `.env.local`，填入绝对路径/Origin/当前已审查 Git SHA。真实凭据不写聊天或 Git。通过已验收 B1 CLI 在新的隔离 DATA_ROOT 初始化账号；不要复用生产数据目录。

```sh
set -a
source modules/projects/integration/.env.local
set +a
modules/projects/candidate/.venv/bin/python modules/projects/integration/ipc-entry.py --migrate --database "$DATA_ROOT/projects/projects.db"
node modules/projects/.preview/modules/auth/dist/src/cli.js bootstrap --username YOUR_LOCAL_ADMIN
node modules/projects/integration/start-website.mjs
```

首次登录需改密；普通用户只能读，账号管理仅 B1 本机 CLI。`start-website.mjs` 不创建账号、不迁移、不启动真实 worker。不要把旧 `candidate serve`、root 旧启动脚本或健康夹具当正式 B2 入口。真实主站仍等待总管收件与后续集成阶段。
