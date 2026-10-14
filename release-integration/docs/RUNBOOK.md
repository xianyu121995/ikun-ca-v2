# ikun.ca 新版最终集成与 Mac mini 上线操作单

本目录是独立的上线准备包。不是新版业务代码，也不是已发布环境。不得把它的 fixture 结果替代业务模块验收。所有命令在 `release-integration` 目录执行；Python 工具仅用标准库，可在本机系统 Python 3.9 运行。业务环境继续遵循新版仓库规定的 Node 24 LTS/Python 3.11+。

## 1. 收件与合并

`config/accepted-modules.example.json` 的六个模块目前默认 PENDING。为每项填最终分支/tag、40 位 commit、验收报告的绝对路径及 SHA256，确认已验收后才改 ACCEPTED。状态字段是交付审查记录，工具本身不能证明报告里的业务结论。

```sh
python3 scripts/release_ops.py intake --manifest config/accepted-modules.local.json
python3 scripts/release_ops.py assemble --manifest config/accepted-modules.local.json --output .runtime/isolated-merge/candidate
```

`intake` 校验仓库基线、提交和报告哈希，输出重叠文件。`assemble` 在新目录 clone，创建 `codex/ikun-ca-v2-final-integration` 并合并固定 SHA；不改变源仓库及他人的 Worktree。冲突保留在候选 clone，不自动采用 ours/theirs。根据模块验收记录解决胶水代码冲突，重新跑集成测试；不得用业务重写掩盖接口不一致。只有总管认可最终候选才回收到新版单仓库 develop。上线工具保存在 codex/integration 的 release-integration 目录，避免覆盖总管的根 scripts/docs。

必须对齐的契约：

- 用户明确要求仅 `superadmin` 与普通只读用户；foundation-v0.1.0 已改为 superadmin/user；仍需验证业务候选消费者。
- canonical project_id、事件 ID、幂等键、revision/ETag，以及人工加入任务的 receipt 要一致。
- Next.js 网站拥有 projects/auth；猎手与 tracking worker 分别只写自己库。Python 独立 API 候选须按此三服务边界完成接入，不能额外启动多个驻留业务服务后声称满足三进程架构。
- 人工加入、收到推文、主页更新均通过受控接口与持久回执，删除某一库的资源不能隐式删除其他库资源。

## 2. 环境与构建

正式路径候选：`~/Library/Application Support/ikun-ca-v2-deployment`。这是新目录，与旧版及总管初始部署目录分别隔离；最终选择一套部署方案，不能同时加载两套新版正式 label。当前不创建此正式路径、不安装正式任务。

```text
ikun-ca-v2-deployment/
  releases/<40位Git SHA>/             clean checkout、固定 Node、依赖与生产 build
  staging/
    config/                          release.local.json、每服务 secret JSON，0600
    data/{hunter,tracking,projects,auth}/   四个独立 DB，每目录0700、文件0600
    plans/<revision>/                三份 plist、冻结 launcher 副本
    logs/ backups/ restore-drills/
  production/                        同样结构，与 staging 完全分离
```

开发窗口端口已有 3100–3912 的分配。本准备包用分配给集成窗口的 staging 4000/4011/4012，production 候选 4100/4111/4112；启动前仍必须查监听占用。全部绑定 `127.0.0.1`，Cloudflare 只代理网站，不暴露两个 worker 的内部接口。

实测 macOS launchd 从 Documents 读取测试脚本出现 Operation not permitted。将代码、Node 二进制、配置与 launchd launcher 放入独立非 Documents 路径后再验收。生成器会冻结一份 launcher 到输出计划内，但配置和 release 本身也必须避开受保护开发目录。不要通过改全局隐私设置或开放所有文件权限解决。

冻结候选后，在自己的 release 依次 `pnpm install --frozen-lockfile`、`pnpm build:shared`、`pnpm typecheck`、`pnpm test`、`pnpm build`、`pnpm smoke`。全部串行，失败即停止；这些命令当前属于未来最终候选检查，不是本包已执行证明。Next.js 运行必须 next start/编译输出。本包要求 BUILD_ID 存在；仅有 BUILD_ID 不能证明版本归属，验收还要记录 build SHA、依赖锁哈希、源提交及端口服务身份。

网站 heap 初始768MiB，worker 初始256MiB，UV_THREADPOOL_SIZE=2；构建按总管 cpus=1 与2048MiB预算。heap 是 JS heap 上限，不是 RSS 硬限。最终压测记录三服务 RSS、Mac memory pressure、swap、业务 backlog 和事件延迟；未测业务负载前不得承诺8GB上的稳定吞吐。

生成新配置（命令里的全大写参数必须替换）：

```sh
python3 scripts/prepare_config.py --root ABSOLUTE_NEW_DEPLOYMENT_ROOT --commit ACCEPTED_40_CHARACTER_SHA --node ABSOLUTE_NODE24_OUTSIDE_DOCUMENTS --environment staging
python3 scripts/release_ops.py validate --config ABSOLUTE_STAGING_CONFIG
python3 scripts/release_ops.py render --config ABSOLUTE_STAGING_CONFIG --output ABSOLUTE_STAGING_PLANS_REVISION
```

工具只创建新的配置/计划，不初始化业务库、不安装或启动服务、不修改 DNS。空 secret JSON 由本机操作员填入最小环境变量；不要在聊天中提供密钥。secret 值不得使用 NEXT_PUBLIC_。启动子进程只继承少量系统变量，不继承旧版的任意凭证。每服务环境配置需要落实库路径；工具的 `databases` 是预检/备份清单，并不自动改写尚未验收模块的存储配置。

## 3. launchd 管理与恢复

输出 labels 为 `ca.ikun.v2.staging.web/hunter/tracking` 或 `ca.ikun.v2.production.web/hunter/tracking`，不使用旧版 labels。KeepAlive=true、ThrottleInterval=30、ExitTimeOut=30、Umask=077、Background。每个服务一个驻留实例，禁止 dev/start 共享同一库。

测试环境由操作者检查生成计划后 bootstrap；可用 `launchctl print gui/UID/LABEL` 检查，`kickstart` 单服务重启，`bootout` 卸载当前测试 label。本包没有批量停止 node/python 或清理旧服务的命令。原生演练脚本只创建随机 drill labels，最终全部 bootout。

生产启动另需用户明确批准。操作员据实际批准生成本地 `production/config/publish.approval.json`，内容绑定 `operation=publish_production`、`approved_by=user`、release_commit 和 release.local.json 的 config_sha256，权限0600。本工具不会自行创建批准记录；该文件是操作留痕，不能替代真实用户授权。修改提交/配置后必须重新审查、重新批准。

用户 LaunchAgent 只在登录会话中运行，注销后不会持续驻留。若要求无人登录的重启恢复，用 `render --daemon-user lvlei` 生成非 root 运行的 LaunchDaemon 候选，在批准后安装到系统域；另验收 FileVault 解锁、文件权限、重启、休眠策略。此次没有改系统配置或进行机器重启。

## 4. Cloudflare、HTTPS与访问控制

`config/cloudflare-v2.example.yml` 是占位的审查模板，不能直接上线。实测 cloudflared ingress validate 通过，ikun.ca 匹配网站4100，其余域名落到404。这只证明配置语法和路由匹配，未验证新 Tunnel/Access 凭证。

批准切域名前，以独立测试 hostname/Tunnel 验证配置；不得重用线上 Tunnel 并改变其现有路由。最终 Tunnel UUID、credentials 文件、Access team 与 AUD 都要本机核实，不能猜。`originRequest.access.required=true` 要求 connector 在代理前验证 Access JWT；没有认证的公网请求应被挡住。网站还必须验证自身登录、两种角色和 CSRF；Access 不替代应用权限。禁止信任浏览器提交的 role、admin header 或伪造 Cf-Access 身份。

保留浏览器到 Cloudflare 的 HTTPS、Cloudflare 的加密 Tunnel；同机 loopback 可以使用 HTTP。若 origin 使用 HTTPS，保留证书验证，不使用 noTLSVerify。管理员页面/业务 API bypass cache，登录/API 限流与 WAF 规则要实际验收；headers/cookies 不得写原始日志。

只读公网探测无法证明新源站上线。HEAD 的302/403只描述边缘访问控制；未认证不能评估当前源站业务。此轮没有创建 Tunnel、改 DNS/Access/WAF、发布正式服务或停止旧服务。

## 5. 备份与回滚

```sh
python3 scripts/release_ops.py backup --config ABSOLUTE_ENVIRONMENT_CONFIG
python3 scripts/release_ops.py restore-drill --config ABSOLUTE_ENVIRONMENT_CONFIG --backup ABSOLUTE_CREATED_BACKUP --output ABSOLUTE_NEW_RESTORE_DRILL_DIRECTORY
```

只备份该配置列出的四库；每库使用只读源连接和 SQLite online backup API，备份转为独立 DELETE journal 文件并做 integrity_check/foreign_key_check、SHA256。不会直接复制运行中 DB/WAL。失败不保留半套“成功备份”。恢复先验证全套哈希，只能写入不存在的 restore-drills 子目录；不会覆盖任何在线库。

四库快照各自一致，不是跨库原子快照。恢复后要按 event_id、inbox/outbox receipt、checkpoint 做业务 reconcile；本轮只验证了 fixture 的持久数据，真实监控 reconcile 尚待最终候选。

日志策略：结构化、脱敏、每服务10MiB×5；数据库备份保留7个每日版本及一次升级前快照，另存一份离机副本。这里是验收要求，自动轮转、定时备份、离机备份尚未安装。launchd 固定 stdout 文件如果没有轮转可持续增长，发布前必须解决。不要在运行中随意 rename 文件后以为日志已换到新路径。

回滚分两个层次：

1. 首次域名切换失败：将已批准的 Tunnel/DNS/Access 路由恢复为切换前快照，旧服务一直保留；检查 HTTPS、登录和关键 API。尚未取得认证配置快照和切换授权，因此本轮未实际演练此层。
2. 后续新版回滚：先验证上一 release 与当前 schema 兼容，只重启对应新版 label到上一完整构建。数据不随代码回滚。若 schema 不兼容，保持相关新版服务停止，保留受损文件，用已验证备份恢复到新路径，再按已审查的迁移/事件重放方案恢复；不做直接 downgrade/覆盖。

上线批准应明确对应候选 commit、正式目录、三个 labels、域名路由变化和可用回滚目标；停止旧服务是单独动作。任何未验收项不因用户批准部署而自动变成已通过。

## 文档依据

- [Next.js 自托管、生产模式与 graceful shutdown](https://nextjs.org/docs/app/guides/self-hosting)
- [Apple launchd 与 LaunchAgent 生命周期](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- [Cloudflare Tunnel 本地配置与 ingress 校验](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/)
- [Cloudflare origin Access JWT 验证参数](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/origin-parameters/)
