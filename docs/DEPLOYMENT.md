> 第二阶段服务/IPC/四库归属以 docs/phase2/STORAGE.md 为准。当前 D0 held，禁止执行本文件部署命令。

# Mac mini M2 / 8GB 本机生产方案（未部署）

目标是原生 Node 24 LTS + 三个独立 launchd 作业 + 本地 SQLite。正式启用、域名切换、Tunnel 修改、旧服务停止和共享 Watch 变更均等待用户明确批准；本次只验证新工程的临时服务并生成可审阅工具。

## 目录与资源

```text
~/Library/Application Support/ikun-ca-v2/
  releases/<git-sha>/       固定提交的构建与各自 node_modules
  config/website.env       网站 secrets（0600）
  config/hunter.env        猎手 secrets（0600）
  config/tracking.env      跟踪 secrets（0600）
  data/hunter/hunter.db
  data/tracking/tracking.db
  data/projects/projects.db
  data/auth/auth.db
  logs/                    有限日志保留
  backups/                 在线一致性备份（不在 Git 中）
  toolchains/node-24.22.0/  固定 Node 二进制
```

此目录是规划；本次不创建/修改此生产目录。DATA_ROOT 不能落在旧版目录或旧版 DB symlink。release 不可变，代码与持久数据分离，回滚只换 release，禁止回滚删除/覆盖 DB。

网站 3100、hunter 3111、tracking 3112，三服务 loopback。初始 Node heap 上限：网站运行 1024MiB，worker 各 256MiB，网站构建 2048MiB；Next cpus=1，构建串行。heap 不是 RSS 总内存上限，也未测业务负载；采集并发初始 2、按实际 memory pressure 调整。不要在生产机同时多窗口构建 Next 或引入 Docker Desktop/Redis/PG。

## 发布流程

1. 总管确认 main/tag、clean Git、锁文件；新 release `pnpm install --frozen-lockfile`，执行 build/typecheck/test/smoke。测试用临时目录，不读生产 DB。
2. 确认生产 DATA_ROOT 是全新 v2；复制 example 并拆成三份最小配置，分别配置需要的 token。Website 不持有 provider key；worker 不持有用户 session secret；跨方向 token独立。
3. 初次上线只建立 v2 库，禁止旧版迁移；后续 schema 变更先一致性备份，再由对应 owner 迁移，校验 schema compatibility。sqlite3 integrity_check/foreign_key_check 验证后启动。
4. 运行生成器输出三份 plist，人工检查绝对路径和服务参数，`plutil -lint`。生成器不会安装或调用 launchctl。
5. 批准后只安装 `ca.ikun.v2.website`、`ca.ikun.v2.hunter`、`ca.ikun.v2.tracking` 到本用户 LaunchAgents。分别 bootstrap、检查状态及 health，不能改旧版 label。
6. 三服务稳定且业务/登录/权限验收通过后，另行批准域名切换。新网站前面配置反向代理/TLS/Access；最终入口仍是 ikun.ca。旧 Tunnel 当前配置完全不改。

生成器用法（需准备真实 release、Node、配置目录、日志目录）：

```sh
node scripts/render-launchd.mjs ABS_RELEASE ABS_NODE ABS_CONFIG_DIR ABS_LOG_DIR
plutil -lint var/deploy/launchd/ca.ikun.v2.website.plist
plutil -lint var/deploy/launchd/ca.ikun.v2.hunter.plist
plutil -lint var/deploy/launchd/ca.ikun.v2.tracking.plist
```

批准后安装/管理的命令模板（本次不执行）：

```sh
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/ca.ikun.v2.website.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/ca.ikun.v2.hunter.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/ca.ikun.v2.tracking.plist"
launchctl print gui/$(id -u)/ca.ikun.v2.website
```

LaunchAgent 需要用户登录 session；注销/重启未登录不能保证驻留。24 小时无人值守若需要重启后立即运行，应另行评审专用低权限账号的 LaunchDaemon、数据权限、FileVault 启动限制及机器休眠设置；本次不改系统配置。KeepAlive + ThrottleInterval=30 防止失败高频重启，SIGTERM drain 10 秒，launchd ExitTimeOut=15。网站/worker 分别重启，不统一杀所有 node/python 进程。

## 验收、日志、备份与回滚

- 进程 health、数据库健康、业务来源心跳、outbox backlog、真实鉴权/租户隔离分别验收；不能用 ready 推断 connected。正式业务未开发前不得宣称生产可用。
- 日志 JSON，不带 secrets/原始事件；生产保留建议每服务 10MB × 5，部署阶段配置 newsyslog 或等价轮转并实测。当前生成器只指定日志路径，不提供已启用的轮转。
- 四 DB 使用 SQLite online backup API 或 `.backup`，不能直接 cp 运行中的 db/WAL。每天备份是部署规划，未创建自动化；定期离线 restore+integrity_check。跨库没有一致性快照，恢复后凭 event_id/receipt/checkpoint reconcile。
- worker 故障只冻结其服务，其他服务可运行。DB corruption 先停止本 v2 服务，保留原文件/日志，验证备份后恢复到新路径；绝不能删除库让系统从零误跑。
- 代码回滚：停止对应 v2 label → 指向之前 release → 兼容 schema 检查 → 启动并验收。schema 不兼容先停止，依 reviewed restore/reconcile 方案，不直接 downgrade。保留当前与上一完整 release。

依据：[Next.js 自托管](https://nextjs.org/docs/app/guides/self-hosting)、[Node LTS 发布](https://nodejs.org/en/about/previous-releases)。launchd 参数在部署机以 `man launchd.plist` 和 `plutil` 验证。
