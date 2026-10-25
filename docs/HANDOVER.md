# ikun.ca 维护交接（给 Mac 上的 Grok Bot）

核对日期：2026-10-25，北京时间。本文记录实际运行状态，不是上线授权。本文中的部署、停止、恢复、SSH 授权命令只是操作说明，本次未执行。所有密码、Token、私钥、登录凭据、助记词只标位置，不提供内容。

## 1. 先读结论与操作边界

- 新接手主线为 `ikun/live`，基于已部署的 `ab3b3d768895741f9a4b36d13568ff5de2245ff4`。四个模块合计 425 个应用源码文件与各自线上 release 比对一致；没有把未上线语音候选和生态代码混入。服务器独有的已部署运维脚本、systemd 定义也已归档入 Git。
- 线上是混合版本，不可把 `/opt/ikun/current` 当作所有进程版本。下面逐服务列出。
- `main` 保持 `63e8a2857241c6a76226f21435e40db9736a1e7e`，本次没有合并、重置、部署或推送。以后是否合并由用户决定。
- 本次只整理本地代码、提交、运行隔离测试、读取线上状态和编写文档。未重启线上服务，未改 Watch，未登录 admin，未查询收费供应商接口，未生成或安装 Grok SSH 钥匙。
- 用户规矩：中文沟通、说人话；今后动手前先问。不得碰 ALPHA 的 Watch 和 `@tampad_`；不得登录 admin；不得读取、传输或代填密钥；删除和花钱由用户自己操作；生产部署和 main 合并需要用户明确批准。
- 老的 AGENTS/阶段规范仍保留。与当前部署事实不同处，以本交接核对证据和用户的新决定为准；不得把本次整理授权延伸成新功能上线授权。

## 2. 仓库、分支、worktree

共享 Git 主仓库：`/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2`。聊天上层目录也有单独 Git 元数据，运行 Git 时务必显式进入下列真实 worktree。

**交接文档 Mac 绝对路径：**
`/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/live/docs/HANDOVER.md`

| 路径（相对于 ikun-ca-v2-worktrees/） | 分支/定位 | 处理建议 |
| --- | --- | --- |
| live | ikun/live；线上应用源码主线、运维原件、交接与验收 | Grok 默认从这里只读开始 |
| hunter-rest-batches | codex/hunter-rest-batches，ab3b3d7；线上猎手来源 | 保留作为来源和回滚参照 |
| wss-receive-audit | codex/tracking-wss-quota，05e0ca2；包含未上线语音候选 | 不是整条可直接部署的线上主线 |
| pending-voice | codex/pending-voice-approval；只保留语音候选，未部署、等用户批准 | 来源05e0ca2；当前提交966cbd6f8a13a4ebe04359eca732fcfda4483048，不能上线时夹带 |
| integration | 当前切换为 codex/ecosystem；生态原有未提交改动已单独提交 9f243bc3076d2ddc2efccc6c34a7a45c03a065f5 | 未部署、等用户批准；不要直接作为生产部署输入 |
| auth / projects / hunter-worker / tracking-worker | 各模块早期独立候选 | 历史开发/冻结证据；未检查每个目录的全部未提交文件，不自动删除 |
| website / homepage-ui / hunter-ui / tracking-ui / c0-lite-control | 历史集成、UI、Mac 控制候选 | 确认所有者、未提交内容、冻结证据和备份后再由用户决定清理 |
| homepage-projects | 早期未形成正常提交的工作区 | 不当作有效上线来源；先人工确认后清理 |

`codex/integration` 原分支仍停在 `aeca6bbbc1b09f1a3e25a82dbd803357972fca9e`；仅把其原 worktree 切换到独立生态分支保存改动。旧主仓库 main 上既存的未跟踪 Auth、Tracking 文件未暂存、未删除。

查看位置与来源：

```sh
cd '/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/live'
git status --short
git worktree list --porcelain
git log --oneline --decorate -20
git show ikun/live:docs/handover/CHANGE_SOURCES.md
```

依赖、数据库、环境文件、运行日志和备份不入 Git。worktree 不能用 rm -rf 随手删除；先保存本地改动，再在用户批准后用 git worktree remove。Mac 旧运行时仍含测试使用的 Node24 工具链，清理前先迁走该工具链。

## 3. 东京服务实际版本

核对证据：`docs/handover/live-inventory.json`、`source-verification.json`、逐文件`source-hashes.json`及`final-readonly-check.json`。短 SHA 仅供阅读，执行操作必须用完整 SHA。

| 服务 | systemd | 实际代码/二进制来源 | 当前执行/监听 |
| --- | --- | --- | --- |
| 网站 Web/Auth/BFF | ikun-web.service | release 7fa16d69fdbc8c7151c46b0dbbcc29b92cc106fb；codex/tracking-wss-quota 的已部署祖先 | run_production.py web；Node24.22；127.0.0.1:4000 |
| 推文追踪 | ikun-tracking-live.service | 同上 7fa16d6；已包含额度保护、只收 WSS、补拉关闭 | run_production.py tracking；Python3.11.15；127.0.0.1:4012 |
| 猎手 | ikun-hunter.service | release ab3b3d768895741f9a4b36d13568ff5de2245ff4；codex/hunter-rest-batches | run_hunter_timefix_ab3b3d768895.py hunter；127.0.0.1:4011 |
| Projects | ikun-projects.service | 现存进程 cwd 是 release 75dd1907e7ddcad481b4de8523963b5fe15198ae；其 Projects 应用源码与 7fa/ab 一致 | 私有 UDS /run/ikun-production-projects/projects.sock；无公共 TCP |
| 健康检查 | ikun-health.service + .timer | /opt/ikun/bin/production_ops.py + current/7fa 下 v2_maintenance.py；另含服务器已有的 REST-only 猎手状态过滤 | oneshot；每 60 秒检查；运行后 inactive/dead + Result=success 属正常 |
| 备份 | ikun-backup.service + .timer | production_ops.py + /opt/ikun/bin/verified_backup.py | oneshot；每天北京时间 04:00，周一另留周备份 |
| 隧道 | ikun-tunnel.service | /usr/bin/cloudflared 2026.10.1，独立二进制，不对应 Git 提交 | metrics 127.0.0.1:65520；ikun.ca、v2.ikun.ca 到网站 4000 |

`/opt/ikun/current` 当前指向 `/opt/ikun/releases/7fa16d69fdbc8c7151c46b0dbbcc29b92cc106fb`。猎手另有固定 release 的 drop-in：
`/etc/systemd/system/ikun-hunter.service.d/90-rest-release.conf`，不会跟随 current 切换。

Projects 启动器读取 current，但旧进程保留原 cwd；因此下次重启会解析 current。此次没有重启。所有上述业务模块源码与 ikun/live 对应；运维归档的本地分支是`ikun/live`；cloudflared是独立安装包，无对应Git分支。新交接提交本身没有上线。

核对时 web、tracking、hunter、projects、tunnel 均 active，NRestarts=0；health/backup 最近执行成功，timer active。Tracking 为 connected，heartbeat/pong 新鲜，error=null。这只是核对时状态，不能保证未来持续在线，也不能用健康全绿宣称历史推文全部找回。

## 4. 登录、用户、目录、存储

现有维护登录别名：
```sh
ssh ikun-server
```

别名保存在 `/Users/lvlei/.ssh/config`：主机 `13.193.157.88`，登录用户 `ubuntu`，已有钥匙文件 `/Users/lvlei/.ssh/ikun_server`。只交接路径，不读取钥匙。不把这个高权限身份直接给 Grok 共用。业务服务用户是 `ikun`，HOME 为 `/var/lib/ikun`，TZ 为 Asia/Shanghai。

```text
/opt/ikun/
  current -> releases/7fa16d69...
  releases/<完整SHA>/             不可变应用源码、构建产物、依赖
  bin/                            Linux 启动、健康、备份与固定版本启动脚本
  venvs/{tracking,hunter,projects}/
  toolchains/node24/
/var/lib/ikun/production/
  config/                         私有环境 JSON、追踪配置、AI、隧道凭据
  data/{auth,projects,hunter,tracking}/
  ops/                            额度账本、状态、授权标记和运维证据
  logs/                           私有运行日志，不能整包输出
  backups/{daily,weekly}/
/etc/systemd/system/               ikun-*.service、timer、猎手 drop-in
```

四个领域数据库必须物理隔离，一领域一 writer，业务代码不得 ATTACH/跨库读写：

| 数据库 | 服务器位置 | schema（本次核对） | 写入方 |
| --- | --- | --- | --- |
| auth.db | /var/lib/ikun/production/data/auth/auth.db | 2 | 网站 Auth |
| projects.db | /var/lib/ikun/production/data/projects/projects.db | 2 | Projects 私有 IPC |
| hunter.db | /var/lib/ikun/production/data/hunter/hunter.db | 5 | 猎手 |
| tracking.db | /var/lib/ikun/production/data/tracking/tracking.db | 4 | 追踪 |

独立只读排查可对各自库使用 SQLite `file:...?...mode=ro` URI + `uri=True`；不要把带 ?mode=ro 的裸文件名当普通路径，会误建文件。不要输出 Auth 全表、密码哈希、session、原始供应商报文。不要复制正在运行的 .db/.wal 作为一致性备份。

Cloudflare 隧道配置 `/var/lib/ikun/production/config/cloudflared.yml`，凭据 `tunnel.credentials.json`。DNS/公网入口由隧道提供，三个业务端口仅回环，不应开放到公网。隧道不等于供应商 WSS，停止隧道只会切断网站访问。

## 5. 当前外部服务、密钥位置、用量

以下文件都是**位置**，禁止 cat、粘贴到聊天或提交 Git。服务器私有环境配置为 0600，程序自行加载：

| 服务 | 使用处 | 凭据/配置位置 |
| --- | --- | --- |
| 6551 | Tracking 被动 WSS；Watch 控制面查询/用户批准的增删；历史 Hunter 支持仍保留但现已停用 | config/tracking.live.environment.json 的 IKUN_TRACKING_6551_TOKEN；config/tracking.live.json；历史 config/hunter.live.environment.json 的 OPENNEWS_TOKEN |
| twitterapi.io | 现在线上猎手所有启用账号的定时推文扫描、用户资料等 | config/hunter.live.environment.json 的 TWITTERAPI_IO_API_KEY |
| 网站/监控 AI | 服务端 Codex CLI；AI 分析实现仍有 gemini.py 的历史文件名，不能据此断定使用 Gemini 计费 | config/ai.json 指定 provider=codex、enabled=true、codex_bin=/usr/local/bin/codex；登录状态 /var/lib/ikun/.codex/auth.json |
| 领域服务互调 | Web/BFF 到 Hunter/Tracking/Projects，方向隔离 | config/web.environment.json、hunter.live.environment.json、tracking.live.environment.json；由启动器加载 |
| Cloudflare | 网站公网隧道 | config/cloudflared.yml、config/tunnel.credentials.json |

这里 config/ 均相对 `/var/lib/ikun/production/`。AI 使用 CLI 默认模型；未查询 Codex 额度，未重新登录，不能承诺免费/无限。文件本身包含登录秘密，不交给聊天或一般代码读取工具。

### 6551 收费与共享账本

用户确认的收费规则：**WSS 每条连接每推送 5 条扣 1 点；获取推文每 20 条扣 1 点；新增 Watch 每次 10 点；删除 Watch 不扣点。** 请求次数不等于点数；双连接若接收同一批消息，会分别计费。

共享 REST 计数：`/var/lib/ikun/production/ops/6551-ledger.sqlite3`，由 `IKUN_6551_LEDGER` 指定；实现 `packages/runtime/python/provider_6551.py`。calls 记录时间、程序、接口、目的、状态码、脱敏错误；meta 保存熔断和缓存。默认全局 REST 日上限 300 次，Tracking 补拉预算 0。不能通过新建账本/清空计数绕过预算。

网站已登录正常用户可从系统健康数据 `/api/v1/system/health` 查看 6551 用量/横幅；后端读取 `ops/6551-status.json`。本次未登录 admin，也没有调用该受保护页面来冒充用户验收。

2026-10-25 核对截面：本地 ledger 当日 Tracking 24 次 REST：Watch 列表 14（200）、新增 4（200）、删除 6（200），未见推文补拉调用。按用户规则新增部分约 40 点，**不是整日总消耗或剩余余额**。10/24 有 Watch 列表 402；10/25 截面熔断 open=false、WSS connected，不能继续把 10/23 的“余额 0”当成现在余额。没有另发请求查询供应商余额。WSS 消息计费不在 REST ledger 中，因此本地 REST 账本无法给出供应商真实总余额。

### twitterapi.io 当前用量

猎手现为 REST-only，不再按“粉丝 5000 上下”分路。只读库看到 **86 个启用 REST 账号、2 个禁用 WSS 遗留账号**；不擅自恢复禁用项。12 个五分钟批次持久调度，每账号约每小时读最新 20 条，批间平摊，重启保留 checkpoint；并发 2，日预算 150000 credits。

本地 quota_daily 按 **UTC 日界**（北京时间 08:00）统计预留，不是供应商账单：
- 10/25：50556（约北京时间 17:03 的截面，随后可能增长）
- 10/24：148128；10/23：132444；10/22：102750。

86 × 24 × 60 约 123840 credits/天，仅是当前扫描基础估算；资料读取、重试和不确定结果会增加。余额与套餐实际费用没有查询，交给用户从官网核实。provider_billing_unknown 必须保留防重扣栅栏，当前看到一个账号有此类轮询错误；不能靠删记录/重置时间戳“修好”。

6551 推文 REST 已禁用，不代表系统没有任何 REST：Watch 事件核对和猎手 twitterapi.io 扫描仍存在。AI 请求也不等于 6551 调用。

## 6. 当前推文、Watch、语音规则

### Tracking

- 只靠 6551 WSS 被动接收。不做断线缺口、重启、新账号初次 REST 拉取；新账号从 Watch 建好以后的 WSS 开始收。
- `IKUN_TRACKING_BACKFILL_ENABLED=0`、`IKUN_6551_BACKFILL_DAILY_LIMIT=0`；代码路径留存但默认关闭，多层入口和 ledger 均拦补拉。不要为测试或恢复临时打开。
- 核对失败/402/unknown/retrying 不应导致 watch_not_active 丢弃 WSS。用户停止/取消、未订阅、归属/身份不符仍拦截。
- Watch 列表仅在启动、WSS 重连、账号增删、手动“检查”时触发；无 300 秒/每小时全量周期核对。启动/重连可合并缓存；失败遵守退避。402 熔断仍允许低频恢复探测，不是永远零 REST。
- 402 识别额度不足，跨进程 REST 熔断，探测间隔从小时级增加、上限 6 小时；WSS 401 重连从 60 秒指数退避到最长 600 秒。不能把 401 一律断言为 Token 失效或余额不足，只能结合供应商证据。
- 网站区分额度不足与实时暂停横幅；“服务在线”不等于外部 WSS 已连上。

### 语音（已部署 7fa16d6 的真实行为）

- 数据源是 `/api/v1/tracking/latest?profile=published-v1&ratings=S,A,B&limit=100` 的新增 activity；SSE 只触发刷新，不从 created 事件直接推断已经播报。
- published-v1 包含 original、quote、unknown，来源不限制 WSS/REST；排除 repost/reply、C/D、未评级、缺失项目。历史残留 REST 仍可能出现在列表；现在不产生新的追踪 REST 补拉。
- 首次列表只建立基线，刷新新增的 activity 才候选。服务器时间减 occurred_at 在 0–10 分钟内才播；缺时间、过旧、未来时间可展示但静音。不补播打开页面前的历史。
- 需要有效会话、本页用户手势启用语音、可用本地语音、连接正常、该订阅未静音；默认北京时间 22:00–08:00 静音，可由用户个人设置调整，静音期间不积压补播。
- 同浏览器通过 Web Locks 选一个播放页，按用户/activity 去重；队列上限 20，候选收到后 30 秒有效，排队过期丢弃。播报内容是“项目名，评级级”，不朗读原始密钥或供应商数据。
- **尚未部署** 05e0ca2 的“播报前再次确认可见/撤回已变为转推的队列项”。因此线上仍可能先 quote/original/unknown 出现并播报，随后改判 repost/reply 后隐藏。不要把这一种情况重复认定为 WSS 漏收；候选修复等用户批准。
- API 401/403 会撤销页面语音、停止拉流。排查“听到了但看不到”应查 activity 类型更新、published-v1、当前筛选和登录状态，不能从一条 SSE created 下结论。

### Hunter 与生态

- Hunter 现用 twitterapi.io REST-only；6551 WSS/Watch 退休分支保持 disabled_rest_only。健康脚本已排除仅由该退休状态引起的错误，其他错误仍报告。
- 东京猎手原第二条 WSS 已退役，用户早期“两条合一节省一半”在这两路生产服务上已不再是当前双连接问题。未来生态监控必须复用现有 Tracking 收件/统一预算，不能另开一条计费 WSS。
- Mac 上 ALPHA/X 的其他连接没有在本次统一盘点，不能据此宣称整个供应商账户只剩一条连接，更不能擅自停它们。

## 7. 只读排查命令

这些检查不需要网站 admin，不调用供应商。不要把 environment、私有原始日志、auth 全表一起输出。

```sh
ssh ikun-server 'readlink -f /opt/ikun/current; systemctl is-active ikun-web ikun-tracking-live ikun-hunter ikun-projects ikun-tunnel; systemctl list-timers ikun-health.timer ikun-backup.timer --no-pager'
ssh ikun-server 'systemctl show ikun-web ikun-tracking-live ikun-hunter ikun-projects ikun-tunnel -p MainPID -p ActiveState -p NRestarts --no-pager'
ssh ikun-server 'systemctl show ikun-health ikun-backup -p Result -p ExecMainStatus --no-pager'
ssh ikun-server 'curl -fsS http://127.0.0.1:4000/healthz >/dev/null && echo web_http_ok'
```

查实际进程版本需 MainPID + `/proc/<PID>/cwd`，猎手还看固定启动脚本/drop-in，不能只看 current。普通 /tracking/latest 接口需要会话；不拿 admin 凭据做 curl。journal 中只提取 audit=wss-receive-v1 或 6551-rest-v1 的脱敏字段；原始日志可能含供应商数据，不要整段粘贴。

漏收结论边界：两端均收到且追踪明确 dropped 才能指出本地原因；单端只算单边收件证据；两端均无记录只说明本机未见收到，不能证明供应商没发。今天 Hunter 已无 WSS，不能再沿用旧“双端缺一”的验收假设。

## 8. 测试与重现

工具链：Node 24.22.x（不要用当前系统 Node25）、pnpm10.33.1、Python3.11.15。Mac 可用 Node 路径：
`/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/toolchains/node24/bin/node`。
Python 测试环境在 live/.runtime/test-venv；它和 node_modules 都是独立、忽略文件，重建不改变生产。

全套本地验收入口（仅临时数据库、合成供应商、回环服务，无线上密码登录、无收费调用）：

```sh
cd '/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/live'
export PATH="$HOME/Library/Application Support/ikun-ca-v2-c0-lite/toolchains/node24/bin:$PATH"
pnpm install --frozen-lockfile
uv venv --python 3.11 .runtime/test-venv
uv pip install --python .runtime/test-venv/bin/python \
  -r services/tracking-worker/python/requirements.lock.txt \
  -r services/hunter-worker/python/requirements-lock.txt
.runtime/test-venv/bin/python release-integration/handover/verify_local.py \
  --python "$PWD/.runtime/test-venv/bin/python" \
  --node "$HOME/Library/Application Support/ikun-ca-v2-c0-lite/toolchains/node24/bin/node" \
  --report docs/handover/verification.json
```

本次当前源码回归**1081项通过，0失败**，TypeScript与生产构建通过；不把Python包装内的Node子用例重复加总。报告 `docs/handover/verification.json`，完整本地日志 `.runtime/handover-test-logs/`。模块分项命令在报告中；Python需加入 packages/runtime/python、对应 worker/python、modules/projects/candidate 的 PYTHONPATH，且先 build:shared/build:auth。网页构建串行，8GB Mac 不并发构建。

覆盖：共享预算/熔断、Hunter、Tracking 全 Python 回归及其 Node 桥接、Projects、Release、桌面 SSH 工具、Auth、根契约、语音、网站 BFF、UI、TypeScript 与生产构建。Auth、Projects、Tracking 旧测试原先依赖某台 Mac 的固定 Node、冻结 preview 和漏打包的共享 Python 模块；本次只调整测试装配，保留断言，并让 SSE 测试兼容心跳先到、双会话旋转用显式 fixture 配置，不更改线上业务源码。

以下旧Projects套件依赖历史preview/独立旧页面，本次未运行：`test_browser.py`、`test_b2_browser.py`、`test_b2_lifecycle.py`。它们的缺失装配不作为当前源码的通过证据。历史 UI 浏览器评审/冻结 preview 脚本不是本次新浏览器验收；未登录生产、未实际发声、未执行真实收费集成。不能把隔离测试通过宣称供应商、余额或每条线上推文验收。

生态分支另有 `release-integration/scripts/test_ecosystem_backend.py`；本次合成数据测试 Hunter298、Projects86、BFF5，共389通过，TypeScript通过。不是生态上线验收。该分支 schema6，而生产 Hunter为5，不可贸然迁库。

## 9. 部署、回滚、备份、恢复（仅未来获批后）

### 部署原则与危险脚本

先让用户批准具体完整 SHA、服务清单、影响时间和回滚点；先做并验证备份。每次确认实际 root/drop-in/进程，固定 release 不覆盖。Web/Tracking 全局 current 与 Hunter pinned root 是两套选择，不能只换 current 就声称全站升级。

- `release-integration/lightsail/deploy_quota_fix.py` **会停止 Tracking 和 Hunter、改配置、切 current 并启动监控，--final 还重启 Web**。它是特定历史修复工具，不能当通用部署脚本随便重跑。
- `activate_production.py` 是 Mac→Tokyo 一次性切换流程，会停测试隧道/Web/Projects、安装生产配置并启用监控，禁止日常复用。
- `install_production_units.py` 会写 systemd 单元，改变后续启动边界；先审查，不能覆盖 Hunter pinned drop-in。
- `mac_cutover.py stop/restore` 会停止/恢复 Mac 作业。恢复可能复活旧收费监控或第二条 WSS，绝不可在东京仍运行时双开。
- 遗留重试/激活/Watch 清理/补拉/类型恢复脚本不自动运行；停服务会丢掉未接收的 WSS，当前没有 REST 补拉兜底。
- 正常构建用 pnpm build；不要把 development .env、数据库、密钥、logs、.runtime、旧 preview 打包进 release。

以下为明确批准后的**只构建/上传候选**命令模板，不自动切流、不执行脚本：

```sh
cd '/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/live'
candidate_sha=$(git rev-parse HEAD)
git diff --exit-code
git archive --format=tar "$candidate_sha" | gzip > "/private/tmp/ikun-$candidate_sha.tar.gz"
scp "/private/tmp/ikun-$candidate_sha.tar.gz" ikun-server:/var/tmp/
# 服务器已有同名 release 就中止，不覆盖。
ssh ikun-server "sudo test ! -e /opt/ikun/releases/$candidate_sha"
ssh ikun-server "sudo install -d -o ikun -g ikun /opt/ikun/releases/$candidate_sha"
ssh ikun-server "sudo -u ikun tar -xzf /var/tmp/ikun-$candidate_sha.tar.gz -C /opt/ikun/releases/$candidate_sha"
ssh ikun-server "sudo -u ikun sh -c 'cd /opt/ikun/releases/$candidate_sha && PATH=/opt/ikun/toolchains/node24/bin:/usr/local/bin:/usr/bin:/bin pnpm install --frozen-lockfile && PATH=/opt/ikun/toolchains/node24/bin:/usr/local/bin:/usr/bin:/bin pnpm build'"
```

依赖安装可能访问软件包仓库，不调用供应商，但仍须部署批准。Python锁定依赖与运行 venv 兼容性应先在候选独立 venv 验证；不能直接 pip 升级共享运行 venv。对于不涉及 schema 的 Web/Tracking 发布，批准并备份后再原子切 current：

```sh
# 仅在用户批准 Web/Tracking 受影响、且确认 Hunter pinned 配置后执行。
ssh ikun-server "sudo ln -s /opt/ikun/releases/$candidate_sha /opt/ikun/.current-approved && sudo mv -Tf /opt/ikun/.current-approved /opt/ikun/current"
# 只重启批准的那个服务；不要复制成全服务重启。
ssh ikun-server 'sudo systemctl restart ikun-web.service'
# Tracking 如需换代码，另经用户批准执行：
# ssh ikun-server 'sudo systemctl restart ikun-tracking-live.service'
```

Hunter 不跟 current；其新 root 需要经审查的固定启动器及 drop-in，明确指向获批 SHA，再只重启 Hunter。本交接不生成新的 Hunter 上线脚本。Projects 有独立长驻进程，是否重启单独列入批准清单。

### 应用回滚

只回代码、不回数据库：先确认 schema兼容，不兼容则停止并请用户决定迁移/恢复。保留回滚前 PID、drop-in、配置文件路径与备份证据，不输出配置值。

Web/Tracking 当前已知回滚点：
```sh
ssh ikun-server 'sudo ln -s /opt/ikun/releases/7fa16d69fdbc8c7151c46b0dbbcc29b92cc106fb /opt/ikun/.current-approved-rollback && sudo mv -Tf /opt/ikun/.current-approved-rollback /opt/ikun/current'
# 按实际批准范围逐个重启：
ssh ikun-server 'sudo systemctl restart ikun-web.service'
# sudo systemctl restart ikun-tracking-live.service 需另有批准。
```

Hunter 当前已知执行项就是 `run_hunter_timefix_ab3b3d768895.py hunter`，服务 drop-in 原件在 `release-integration/lightsail/deployed-systemd/`。未来若变更 Hunter，要在变更前备份这份 drop-in 和启动器；获批回滚时恢复原件、daemon-reload、仅重启 Hunter。不要直接回退到 `run_hunter_rest_7111ce3.py`，那是修复微秒窗口前的旧版本。

### 备份

服务器已定时做四库独立 SQLite online backup，逐库事务快照，核对 integrity、foreign_key_check、所有表计数；四库不是一个全局事务快照。最近已核验的日备份：
`/var/lib/ikun/production/backups/daily/20261025-040004-173674`。
四库均 integrity=ok 且全部表计数匹配。备份含账号秘密，应0600/目录0700，不发聊天、不进Git。

用户批准后可手动触发现有备份：
```sh
ssh ikun-server 'sudo systemctl start ikun-backup.service'
ssh ikun-server 'systemctl show ikun-backup.service -p Result -p ExecMainStatus --no-pager'
# 单次独立备份的等价入口，仅供获批操作：
ssh ikun-server 'sudo -u ikun /opt/ikun/venvs/projects/bin/python /opt/ikun/bin/verified_backup.py --root /var/lib/ikun/production/data --destination /var/lib/ikun/production/backups/manual'
```

Mac `ca.ikun.lightsail.backup-pull` 仍注册，每天04:30拉服务器已验证备份到：
`/Users/lvlei/Documents/ikun-ca-backups/lightsail`。
这不是旧业务监控，不要为了停旧服务把它一起关掉。目录仍在同一 Mac 上，不等于异地备份。

### 恢复

恢复先在**全新隔离目录**演练。停止写入、选择完整已验证快照、检查 schema/计费栅栏/去重水位，再恢复生产；每步单独得到用户批准。不能直接把四个旧 .db 覆盖现库，更不能在服务活着时复制/删除 WAL。Auth恢复可能回退密码/会话；Projects恢复需核对 outbox/inbox 和其他领域，避免重复命令。

普通快照的只读验证（不打印业务行）：
```sh
ssh ikun-server 'sudo -u ikun /opt/ikun/venvs/projects/bin/python -c '"'"'import sqlite3; from pathlib import Path; p=Path("/var/lib/ikun/production/backups/daily/20261025-040004-173674"); [(print(role, sqlite3.connect((p/(role+".db")).as_uri()+"?mode=ro", uri=True).execute("PRAGMA integrity_check").fetchone()[0])) for role in ("auth","projects","hunter","tracking")]'"'"''
```

领域恢复工具的参数与约束：

```sh
# Hunter：bundle 是 retention.py 生成、带 manifest 的目录；daily 四库快照不是这个 bundle。
# 必须使用当前已停止的最新库保留计费/调度/去重栅栏，destination 为新的空路径。
PYTHONPATH=packages/runtime/python:services/hunter-worker/python \
  .runtime/test-venv/bin/python -m hunterradar restore \
  --bundle /approved/hunter-bundle --destination /isolated/recovered-hunter.db \
  --current /approved/stopped-latest-hunter.db

# Tracking：需与其备份配套的 ledger，expected-watermark 来自停机后的最新只读水位。
PYTHONPATH=packages/runtime/python:services/tracking-worker/python \
  .runtime/test-venv/bin/python -m tracking.cli restore \
  --config /isolated/recovery-config.json --backup /approved/tracking-backup \
  --ledger-source /approved/stopped-latest-tracking.db --expected-watermark WATERMARK
```

Hunter恢复会拒绝不一致的 REST checkpoint/不确定计费状态；不要删表或降低检查来绕过。Tracking配置必须指向隔离目标，不得默认读取生产。通用 daily备份恢复到隔离库可用 sqlite3 backup API 再验证；将结果替换生产库前仍需领域恢复检查和用户批准。这些演练本次未执行。

## 10. 已知问题与下一步

1. **语音候选未上线**：codex/pending-voice-approval 从05e0ca2分离。上线前审查延迟确认/更新撤回行为、按具体SHA批准。
2. **连接合并状态**：Tokyo Hunter WSS 已退役；未来生态不要再开第二条连接。整个供应商账户其他Mac程序未盘点，不碰ALPHA。
3. **多余 Watch 待用户清理**：10/23历史快照曾见Tracking122个、3个组（117+4+1）；当天猎手19个Watch及5空组已处理。10/25账本已有增删，旧122不是当前核验数。本次不拉新列表、不做清理。必须新证据+归属清单+用户自己操作，排除ALPHA/@tampad_。
4. **搜索带 @ 搜不到**：保留为待办，本次没有修复或改搜索规则。
5. **生态监控未上线**：codex/ecosystem保存原后端改动；先解决预算、复用收件连接、适配当前REST-only猎手、schema迁移与产品验收，不能直接合入主线部署。
6. **twitterapi.io余额与不确定计费**：实际余额需用户官网核对。150000是本地保护额度，不是余额。不得自动付费重试、清计数或绕过provider_billing_unknown。
7. **历史丢推无法凭健康推断找回**：Tracking补拉已完全关闭，离线缺口可能永久缺失；不拿用户同意后的被动接收规则去承诺历史完整性。
8. **AWS免费计划**：用户要求在2027-04前升级/确认账单与续费；本次未登录AWS确认权益，建议用户提前安排。
9. **Mac旧服务保留**：旧C0-lite Web/Hunter/Tracking-live已从launchd停用，data_deleted=false；Tokyo切换证据位于旧runtime/ops/lightsail-cutover/mac-stopped.json。旧库、配置、快照都保留。建议至少保留到2026-11-25且完成一次异地恢复验证，再由用户决定删除；这不是已确定保留期。
10. **定时核对**：“ikun 两路 WSS 漏推核对”(ikun-wss) 在本机自动化注册表已不存在，确认没有启用，没有为暂停而重建；“VOUT 50账号每日检查领取”(vout-50)保持ACTIVE，原配置哈希未动。不要把本任务旧heartbeat指令当作新授权继续查或创建WSS。
11. **账号工具**：桌面“ikun账号管理.command”“创建ikun管理员.command”来源ce38b503，已改成ssh -t到Tokyo服务用户的CLI；新网址ikun.ca。旧Mac auth库只作历史，不再作为线上账号来源。不替用户创建账号或输入密码。

## 11. Grok权限与独立SSH钥匙计划（尚未执行）

Grok需要的起步权限：只读仓库/文档、指定worktree内编写候选代码及跑隔离测试；受限SSH读取指定服务状态、脱敏journal和业务元数据；不能读Auth秘密/原始日志/环境凭据。生产写入、sudo、部署、重启、Watch、付费API、删除和GitHub推送都按用户逐项授权。

**同一Mac用户的两个Bot天然能访问同一用户文件；仅生成另一把SSH钥匙不能隔离现有钥匙。** 建议用单独macOS账户或真正的文件沙箱运行Grok，禁止访问旧 `~/.ssh/ikun_server` 和全部生产秘密。服务器建议新建 `grok-ikun` 账户，从无sudo起步，不复用ubuntu的广泛权限。必要时由用户批准安装仅输出脱敏状态的受限维护命令；直接给systemd-journal组也可能读到无关秘密，不能当最小权限。

**等用户确认后**，由用户在终端手动生成（隐藏输入口令，不用-N传口令）：

```sh
ssh-keygen -t ed25519 -a 100 -f "$HOME/.ssh/ikun_grok" -C 'grok-ikun-20261025'
chmod 600 "$HOME/.ssh/ikun_grok"
ssh-keygen -lf "$HOME/.ssh/ikun_grok.pub"
```

新私钥留在Grok获准的本机用户目录/SSH agent，不发聊天、不上传。只安装 `.pub`：

```sh
# 以下创建账号、改服务器文件均须用户事先确认，本次未执行。
ssh ikun-server 'sudo adduser --disabled-password --gecos "" grok-ikun; sudo install -d -m 700 -o grok-ikun -g grok-ikun /home/grok-ikun/.ssh'
scp "$HOME/.ssh/ikun_grok.pub" ikun-server:/var/tmp/ikun_grok.pub
# from=应由用户指定真实可信出口CIDR；不确定时不要猜。
ssh ikun-server 'sudo sh -c '"'"'printf "restrict " >> /home/grok-ikun/.ssh/authorized_keys; cat /var/tmp/ikun_grok.pub >> /home/grok-ikun/.ssh/authorized_keys; chown grok-ikun:grok-ikun /home/grok-ikun/.ssh/authorized_keys; chmod 600 /home/grok-ikun/.ssh/authorized_keys'"'"''
```

`restrict` 禁止端口/agent/X11转发和PTY，适合起步只读非交互命令。尚未授予读生产目录的ACL，更没有sudo；先限定脱敏读取命令，不能为“方便”开放整个/var/lib/ikun。需要交互TTY管理账号时应由用户操作，不给Bot开放admin管理。

在Grok用户的ssh config单独添加：
```sshconfig
Host ikun-grok
  HostName 13.193.157.88
  User grok-ikun
  IdentityFile ~/.ssh/ikun_grok
  IdentitiesOnly yes
  ForwardAgent no
```

**撤销步骤**：用户先核对 `ssh-keygen -lf ~/.ssh/ikun_grok.pub` 指纹，服务器备份authorized_keys后仅删除注释/指纹匹配的新Grok公钥行；撤销给grok-ikun的任何ACL/受限sudo/部署权限；如需立即失效，批准后结束该账号现存会话。不要删现有ikun_server公钥，不停止ikun业务。最后由用户移除本机Grok私钥和agent缓存。完整撤销命令可由用户在确认准确公钥后执行：
```sh
# 只移除唯一Grok注释行；先验证匹配仅1行，不打印行内容。
ssh ikun-server 'sudo test "$(sudo grep -c "grok-ikun-20261025$" /home/grok-ikun/.ssh/authorized_keys)" = 1 && sudo cp -p /home/grok-ikun/.ssh/authorized_keys /home/grok-ikun/.ssh/authorized_keys.before-grok-revoke && sudo sed -i "/grok-ikun-20261025$/d" /home/grok-ikun/.ssh/authorized_keys'
# 现存会话不会因删除公钥自动断开；终止仅Grok账户会话需另获用户批准。
```

## 12. 是否用私有GitHub备份

建议使用**用户自己创建的私有仓库**存源码、文档和分支，启用2FA、最小协作者权限及受保护主线；Grok先只读/提PR，main由用户决定。当前本地仓库未配置remote，本次未创建仓库、未添加remote、未push。

首次推送前扫描**全部历史和所有准备推送的分支**，不只查当前文件；移除/妥善处理任何历史秘密，禁止提交DB、WAL、Auth登录状态、环境JSON、私钥、备份和原始日志。GitHub的secret scanning覆盖历史，但私有仓库可用能力取决于套餐，不能把“私有”当成秘密保险箱。参考[GitHub官方说明](https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning)。

Git只备份代码，不备份线上业务数据。数据库需另做加密、异地、可恢复验证的备份，密钥保管由用户负责。
