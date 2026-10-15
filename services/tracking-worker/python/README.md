# ikun.ca 独立 NEW_TWEET 引擎 · B3

只读写 `DATA_ROOT/tracking/tracking.db` 及其 WAL/SHM。`serve` 在独立 Tracking 进程中运行 API 和采集；网站退出/重启不控制该进程。默认关闭真实 6551，不复用旧版账号或 Watch。

当前是本地集成候选，未合并/部署。完整构建和新浏览器验收因总管 C0-lite 资源优先安排暂停；旧轮构建/截图不证明当前源码通过。精确结果及限制见 `HANDOFF.md`、`B3-WORKLOG.md`。

## 身份与接入

人类登录、页面、Route Handler、Server Action 和 SSE 撤销使用固定 B1 实际 guard。仅 superadmin 写，user 只读，强制改密会话不能进入业务。Worker 仅接受独立方向 `TRACKING_API_TOKEN`（至少32字符，不能等于 provider token），不接收人类 Cookie、不提供本地登录、不读取 auth.db。旧 `/api/tracking`、静态登录、session getter 和直连 Worker 的 Nginx 模板已退役。

网站候选在 `integration/website/`；UI 固定 `d90598f4bc595458ce26c5ee1c2e1618e318abc0`，最小补丁为 `integration/patches/tracking-live.patch`，不改公共组件/CSS 或其他 Worktree。直接加入先经固定 B2 IPC 校验 canonical `prj_UUIDv4`；Hunter→Projects→Tracking 使用 B2 真实序列化 outbox，不直接打开其他库。

## 独立运行

Python 3.11+、Node24、固定 B0 runtime；发布必须包含仓库 `schemas/tracking`，不支持丢失 SQL 的单独 wheel。依赖安装/完整构建遵守同一重任务锁，当前优先时段未解除前不执行。

```sh
uv venv --python python3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
uv pip install --python .venv/bin/python --no-deps -e .
cp config.example.json config.local.json
```

首次创建可复制示例；已有配置先检查，不覆盖。填写 `db_path` 为自己的绝对 `DATA_ROOT/tracking/tracking.db`，配置0600的 `token_file`（独立6551账号）和 `service_token_file`（Tracking方向凭据）。网站通过服务端环境提供相同方向凭据及 `TRACKING_API_URL=http://127.0.0.1:<本窗口端口>`；不得使用 NEXT_PUBLIC_* 或交给浏览器。

```sh
.venv/bin/python -m tracking.cli init --config /ABS_CONFIG/tracking.json
.venv/bin/python -m tracking.cli serve --config /ABS_CONFIG/tracking.json
```

`init/migrate` 是唯一迁移入口；`api/worker/serve` 和 ready 仅校验。`api` 只运行 HTTP、`worker` 只运行采集，常规选择 serve。loopback 示例端口3112，开发窗口须另配独立端口。固定 B0 集成后：

```sh
IKUN_TRACKING_CONFIG=/ABS_CONFIG/tracking.json \
IKUN_TRACKING_PYTHON=/ABS_RELEASE/services/tracking-worker/python/.venv/bin/python \
DATA_ROOT=/ABS_DATA \
/ABS_NODE/bin/node /ABS_RELEASE/scripts/service.mjs tracking start
```

入口使用 B0 spawnManaged guardian，裁剪子进程环境、协调 SIGTERM、回收父进程异常退出的私有树。`deploy/ca.ikun.v2.tracking.plist.example` 仅待审，未安装。缺 IKUN_TRACKING_CONFIG 时仍是基础 idle，不代表监控运行。

## API

公开候选前缀 `/api/v1`；标准 `{data,request_id}`、错误code/no-store。写入需要 B1 Origin/Host/CSRF 和 UUID Idempotency-Key；修改/状态操作需要 `If-Match: "rev-N"`。路径用 sub_ID，不能拿 project_id 代替。

| 方法 / 路径 | 行为 |
|---|---|
| GET /tracking/subscriptions | 订阅分页及 desired/observed/operation/connection 四种状态 |
| POST /tracking/subscriptions | project_id/name/x_user_id/x_handle/notes/confirmed:true；202仅持久受理 |
| GET/PATCH /tracking/subscriptions/{sub_ID} | 查询、编辑本订阅名称/备注；账号不可静默替换 |
| POST /tracking/subscriptions/{sub_ID}/{start,stop,resume} | 异步命令202 |
| DELETE /tracking/subscriptions/{sub_ID} | 异步移除，保留历史、不修改主页 |
| GET /tracking/latest、/tracking/activities | 接收时间分页的脱敏动态 |
| GET /commands/{cmd_ID} | 先查固定 Projects 网关，只有真实 NOT_FOUND 才回查 Tracking |
| GET /tracking/events | 本地SSE候选：标准envelope/Last-Event-ID/持续撤销；统一events网关由总管集成 |

Worker `/internal/v1/commands` POST/GET 使用固定 B2 CommandEnvelopeV2；内部不额外要求公共幂等/If-Match头。command_id inbox hash 和 envelope.expected_revision 保证幂等/版本。结果固定8字段；ACK丢失查原ID；DB故障503，不能假404后重发。

内部还提供 subscriptions/latest/activities/events/status/outbox。`/health/live` 只证明进程存在，ready只证明本库兼容。观察 outbox 保持 pending/可查询：固定 B2 ingest/tracking=501，未发送或伪造回执。

## 远端与恢复

- confirmed 后先事务持久命令/订阅/审计再202；add/delete后完整回查 Watch。ACK、超时、本地desired不当成功；停止确认absent后才显示已停止。
- 每个项目最多一个sub_ID；恢复沿用ID、递增generation并重建baseline。X稳定ID只补缺值，冲突409，不覆盖人工名称/备注。
- ownership reservation、revision fence、单worker租约持久化；重启先回查，不确定写入不盲重发。600名额满额只报错/退避，用户手动移除，不自动淘汰。
- 仅操作本模块已声明、groupName/全部flags匹配的记录；外部编辑、未知归属、列表不完整均阻止变更。分组不等于账号隔离，真实启用仍需独立账号与明确授权。
- HTTP超时/串行限速、429/Retry-After、退避抖动；WSS ACK/pong超时、断线重连、REST恢复。connected需要新鲜worker心跳和来源pong。
- 同代按 `(subscription_id,generation,tweet_id)` 去重；WSS/REST/重放及空正文补全不新增动态。WSS未知发生时间保留null；REST缺可靠时间不作为恢复新推文。
- REST仅最近100条，超窗标记possible_gap；不承诺无限历史、不新增定时清理。

## 未决与未验证

C-01全量发布时间跨页倒序、C-03全量评级组合来源/分页、C-05跨generation公共折叠仍BLOCKED。保留冻结接收时间排序，UI标明页内筛选；真实订阅备注在账号/正文前。评级只取授权Projects API实际值；媒体/互动/重要标记未知，不伪造0/false。转推/回复/引用与保留期待定，历史候选过滤不能称为产品定稿。

真实6551、付费/Watch操作、主站合并、域名、生产launchd/Tunnel、跨worker全链路尚未验证。测试仅私有临时库及MockTransport/loopback，不接触旧资源。

## 验证

```sh
.venv/bin/python integration/sync-b3.py
.venv/bin/python integration/bind-b3.py
.venv/bin/python -m pytest -q
.venv/bin/ruff check tracking tests integration --select E4,E7,E9,F,I,UP
```

pytest包含1个Node/B1/B2实际入口wrapper，其内部6项不再累加；进程/WSS用例需要loopback权限。新装机先用prepare-b3.py导出固定Git输入，再安装冻结依赖/构建，不merge本分支。

优先时段明确解除后，完整构建使用主仓库同一把锁：

```sh
python3 /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/scripts/with-heavy-lock.py \
  --owner tracking-worker --timeout 600 -- .venv/bin/python integration/build-b3.py
```

compiled生命周期入口 `integration/tests/lifecycle.test.mjs`；浏览器批次 `integration/tests/browser.test.mjs` 的整个预览生命周期也须包在此锁内。不得复制/删除锁或因锁空闲跳过C0安排。日志/输入哈希在忽略的artifacts/b3；旧日志不代替最终源码验证。
