# B4 精确集成交接（仅冻结后收件，不自行部署）

本批精确协议已获579a57f2e3e470525eb53f9f1f85ba75d25f3728批准；原协议b16fb36a8b8269350319c02a60faa6ea2708d95a。当前实现待总管按最终Git HEAD审查冻结；源路径/hash、SQL/hash及全部可收件映射见同目录RECEIVING-B4.json，测试总表见../docs/b4/night-receipt.json。不要整体复制本Worktree或preview。

## 固定依赖与边界

- phase2 9699375c920465b5d802e7acff17b5421203e544；B4放行63e8a2857241c6a76226f21435e40db9736a1e7e；B0工具/脚手架85be3bd6dce25d82033b6cb1a7157aaa39bd571e。
- Auth f097bd4722155d5e689b8894956391ed7e5f2fa7（密码至少10）；Projects cc95dc27852d056457ca0582cff64a88c0eab1d4，最小constructor修复审阅967f3098e84de7e299d970019d56b571ac63de94；原B2业务/模型d0fdefab2aa230ebb8df856aed306d0184d362e2不改。
- 公共UI 486294ac3255b08fdb13a307ee15f96c571020d9；Hunter UI 08065d700239b20fb4c887bbd0c85321904687f8。新补丁仅两个v3文件：live callbacks/权限/错误/正式字段长度/grade C/D/null/游标衔接/真实X链接/待核实文案，原型数据不用于live fallback，公共组件与v3.css不变。
- 数据库唯一writer仍Hunter，仅hunter.db。禁止接入旧Hunter目录/账号/DB、共享Watch、其他库/WAL、其他服务label/端口/日志；没有安装launchd、改CF/DNS、合main或部署。

## 源路径到正式映射

| 源 | 正式目标/方式 |
|---|---|
| services/hunter-worker/src/main.ts | 同路径编译dist/main.js，Node24 execve Python；必须HUNTER_ENGINE=python |
| services/hunter-worker/python/hunterradar/*.py | 同路径发布；PYTHONPATH指向此python目录，保留repo相对schemas布局 |
| schemas/hunter/001_foundation.sql、002_hunterradar.sql、003_b4_protocol.sql、004_research_retention.sql | 同路径，只由Hunter显式迁移；001/002/003已有版本不得改写 |
| integration/website/lib/hunter.ts | apps/website/lib/hunter.ts，服务端BFF与Hunter命令/SSE贡献 |
| integration/website/components/hunter-controller.tsx、hunter-host.css | apps/website/components/同名；CSS仅解除父脚手架main的max-width/margin，不改冻结布局 |
| integration/website/app/hunter/page.tsx、actions.ts | apps/website/app/hunter/同名；每入口真实B1校验。最终UI入口由集成与原owner协调 |
| integration/website/app/api/v1/hunter/[...path]/route.ts | apps/website/app/api/v1/hunter/[...path]/route.ts；不能仅依赖Proxy |
| integration/patches/hunter-live.patch | 对Hunter UI08065d7的apps/website/features/hunter-discovery/v3/App.tsx及model.ts做git apply --check后最小接线；base/hash不匹配退回协调，禁止force覆盖 |

按RECEIVING-B4.json逐文件核对hash。公共UI和既有Auth/Projects文件不由本批覆盖。preview固定cc95 helper并在Hunter页调用其projectsAuth，实际验证跨bundle策略；正式站沿已获批的Projects helper，不从Hunter复制第二套Auth。

**不得映射** var/b4/preview、integration/tests/fixtures/action-probe.tsx、测试挂载的commands/events路由、临时账号/夹具DB、.env、venv、node_modules、.next、截图到网站公开目录、旧私有静态页面或保留services/hunter-worker/ui。

## 运行包与独立job

运行结构保留 release/services/hunter-worker/{dist,python/hunterradar} 与 release/schemas/hunter，Node依赖已批准的@ikun/runtime/@ikun/contracts compiled包。Python>=3.11，安装python/requirements-lock.txt的精确版本，根pnpm-lock保持原owner冻结，不新增第三方包。依赖锁及SQL完整SHA256在收件JSON。

Python只安装依赖到独立受管venv；运行通过显式PYTHONPATH，不把模块复制到site-packages后让SQL_ROOT相对路径失效。Node必须24且支持execve；HUNTER_PYTHON_BIN是部署venv绝对路径。DATA_ROOT是v2自有数据根，不能指向Worktree/preview/旧服务；job cwd是独立0700私有目录且无.env。只读release与可写数据/日志分开。launchd由集成创建全新v2 label/端口/job，不使用旧label；本窗口只交可启动入口。

以下是可复用命令模板，绝对路径由集成固定到收件release；不含任何真实秘密，未执行部署：

```sh
export HUNTER_RELEASE=/absolute/accepted/release
export HUNTER_PYTHON_BIN=/absolute/private/hunter-venv/bin/python
export PYTHONPATH="$HUNTER_RELEASE/services/hunter-worker/python"
export DATA_ROOT=/absolute/private/v2-data
export HUNTER_DB="$DATA_ROOT/hunter/hunter.db"
export HUNTER_ENGINE=python
export HUNTER_V2_MODE=1
export HUNTER_TENANT_ID=ikun-main
export HUNTER_HOST=127.0.0.1
export HUNTER_PORT=3311
export HUNTER_EXTERNAL_IO_ENABLED=0
export HUNTER_REQUIRE_EXTERNAL_IO_DISABLED=1
export HUNTER_DELIVERY_PROTOCOL=v2-event
export HUNTER_PROJECT_DELIVERY_ENABLED=0
export HUNTER_SECRETS_FILE=/absolute/private/hunter-secrets.env
cd /absolute/private/hunter-job-cwd
"$HUNTER_PYTHON_BIN" -m hunterradar init
"$HUNTER_PYTHON_BIN" -m hunterradar status
/absolute/managed/node24 "$HUNTER_RELEASE/services/hunter-worker/dist/main.js"
```

端口3311是独立本地示例；正式新job由集成分配自己的未占用v2 loopback端口，并绑定IKUN_HUNTER_ORIGIN，不占旧服务。secrets文件由操作者设置0600/父0700，包含独立随机>=32字符HUNTER_API_TOKEN，不能复用session/provider/反方向key，不写进交付或日志。

已有Hunter库升级：先停本job（不要停其他job），再执行同环境`python -m hunterradar migrate`。迁移前online backup校验成功才DDL；支持foundation/2/3升级到4、三/四列ledger，歧义稳定ID阻断回滚，拒绝外来/未来版本/软硬链接。不允许serve/readiness自动建库；新库也必须先init。旧二进制拒绝schema4，不降user_version或删账本回退。

## 恢复与发布边界

```sh
"$HUNTER_PYTHON_BIN" -m hunterradar restore   --bundle /absolute/private/hunter/recovery/retention-UUID   --current /absolute/offline-latest-source/hunter.db   --destination /absolute/new-empty-recovery-path/hunter.db
```

current必须由操作者确认是已停服务、受控真实最新Hunter源；程序检查身份/版本/lease、持写锁捕获栅栏，并拒绝bundle自身、同inode/软硬链、已标恢复副本。缺源/无法确认最新性必须停止；任意旧副本不能证明备份后未来状态。目的地须全新，失败不覆盖原库。

R4：恢复先写非hunter.db的私有`.hunter-restore-UUID.tmp`（Store无条件拒绝该名字），合并最新ledger/不可变cmd/evt/hash/posted/receipt/额度和SSE sqlite_sequence空洞高水位，过期过滤、提高revision/轮换cursor、checkpoint/完整性校验/fsync完成后，独占创建无效空目的文件并原子replace发布。硬退出前目标不存在或无效；发布后只有已完成栅栏。不是用except写invalid标记冒充SIGKILL安全。恢复失败保留私有不可激活临时证据，恢复命令/本库维护按3份/48h清理此类副本；无进程运行时由操作者执行受控恢复/清理，不手工把tmp改名激活。

备份自身最多3份/48h，失败副本到期只留小错误记录；实际备份deadline8秒，低于批准30秒上限。恢复目标验证通过后先离线核对，再由集成选择新DATA_ROOT启用；不得同时激活原源和恢复副本。恢复不会创建Projects/Tracking数据或重发已posted事件。

## 外采关闭、预检与受控内部回执

compiled入口拒绝HUNTER_EXTERNAL_IO_ENABLED非0、移除provider key继承并强制require-disabled；正式Settings不读cwd .env。health/ready返回schema_version=4、external_io_enabled=false、source_status=“未连接真实来源”、project_delivery_enabled真实开关；ready仅存储健康。浏览器live明确未连接，有夹具另标“本地验收夹具”，不能把本地fixture心跳当真实来源。

项目受控内部回执独立于外采：冻结接线后集成可设置HUNTER_PROJECT_DELIVERY_ENABLED=1，HUNTER_PROJECT_TASK_URL=http://网站loopback端口/internal/v1/ingest/hunter，以及独立PROJECTS_INGEST_HUNTER_TOKEN（server secret file）。先查/internal/v1/receipts/hunter/{原evt_ID}，首次POST前posted持久化；未知/404只核对不盲重发。不是直接连接Projects DB，也不直接给Tracking建任务。当前验收HTTP receiver为MockTransport夹具，正式网站IPC/Tracking链还须集成验收。

## BFF / SSE / Action

网站环境使用固定loopback IKUN_HUNTER_ORIGIN与HUNTER_API_TOKEN；浏览器Cookie只给B1，worker只收到BFF刚验证的principal与方向token。user读signals/detail，superadmin写账号/研究/人工确认；账号列表仅superadmin管理用途，不渲染归因名单。

- GET /api/v1/hunter/signals、/discoveries/{dsc_ID}：标准脱敏投影；signals为当前72h资格，detail最长七天。
- GET/POST /api/v1/hunter/accounts；PATCH/DELETE /accounts/{account_id}：本v2本地配置，不改共享Watch。
- PATCH /api/v1/hunter/discoveries/{dsc_ID}：ProjectFields非空subset、If-Match/UUID、最小写回执，GET刷新；same key核对unknown，无demo fallback。
- POST /discoveries/{dsc_ID}/monitoring-requests：完整ProjectFields+confirmed=true；202只是持久受理。确认A后草稿B不能冒充原A，R1回归固定。
- confirmHunterMonitoring Action同样在函数体B1校验，同源CSRF/user/撤销不能依赖Proxy。preview-only probe已实测四种结果，不上正式站。
- hunterCommandRoute是既有GET /api/v1/commands/{cmd_ID}的Hunter来源分支；hunterEventsRoute是既有GET /api/v1/events/stream的Hunter贡献，内部/internal/v1/events读取sequence，标准id hunter:N，15秒心跳重验。**不能覆盖其他来源的全局commands/SSE**；多来源cursor/路由组合归C0，接收者保留现有Projects/Tracking。

研究不注册canonical、不改Projects评分、不加入主页。已确认snapshot不可变；过期后命令恢复独立存在，posted不回退，迟到receipt只能更新原任务。语音本批不实现。

## 验证及剩余门禁

227项Python（含原130/历史69，不重复计数）、10项Node、14组正式Next/B1/Hunter浏览器、11组私有兼容、3次主进程启动+事务硬退出、5处恢复SIGKILL边界。实际命令/receipt/hash见night-receipt.json与final-batch.json。原型文件12个hash逐一一致，原失败证据保留。

真实6551/REST/付费、旧服务/Watch、受保护站发布及真实Projects→Tracking/600名额整链未由本窗口执行；本地fixture PASS不充公网/实际来源验收。缺可靠follow时间按原来源策略披露，D1/D8已确认，语音held/归他owner。总管冻结后集成才可按本清单收件新v2 job，无需等B3冻结，但本窗口不自行合并或部署。

网关增补：已读取8b84ee97a94bae28e98b550b2721991f30088486的SITE-GATEWAY-ADDENDUM.md。核心冻结后由集成新增只读/api/v1/hunter/events委托本已验handler，保留hunter:N与B1每块/心跳撤销，controller补有界可取消SSE触发现有load；原Projects全局流保留，不造复合cursor/bus/DB。该alias与接线patch由集成另验，本candidate不为alias改写或假称已上线。
