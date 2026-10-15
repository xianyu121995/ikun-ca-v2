# 夜间逐模块接入准备

授权依据：Git对象 `579a57f2e3e470525eb53f9f1f85ba75d25f3728`。当前运行仍是已验收的 `c1fe12d32ec6f23dbc97f712dab565b7c0c7855f`。本目录只有收件门槛和作业工具，不包含未冻结worker业务源码，不代表新worker已部署。

`intake.json`把两worker明确保持 `WAITING_ACCEPTED_FREEZE`。协议提交不是实现验收；收到总管逐个完整冻结SHA后才填写接受来源、依赖和精确hash，前向merge到现有codex/integration。不能把其他worker未完成当成当前已冻结worker的发布依赖。

## 独立运行位置

沿用现有根 `/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite`，不创建第二套网站，不改v2 Tunnel。网站现有label/4000不变。

| worker | 新label | loopback候选端口 | 唯一数据库 | 新工作目录 |
|---|---|---|---|---|
| Hunter | ca.ikun.v2.c0lite.hunter | 4011 | data/hunter/hunter.db | jobs/hunter |
| Tracking | ca.ikun.v2.c0lite.tracking | 4012 | data/tracking/tracking.db | jobs/tracking |

端口只是候选，实际安装前检查占用；不能停止占用端口的旧服务。各自 `config/<worker>.environment.json`、logs/<worker>.log/error.log，配置/日志0600、目录0700。Python生产依赖用各自venvs/<worker>和最终冻结lock，不复用开发venv/旧凭据。Node固定现有toolchains/node24，worker heap256MB是每Node限制，不是OS RSS硬上限。

## 工具与技术门槛

`../scripts/night_worker_ops.py`只用标准库，提供render/check/run/unload；render不会调用launchctl或安装作业。它复制一份固定launcher进新计划目录，plist每次启动都会重新preflight。缺accepted_frozen立刻拒绝，因此待收件计划即使被误加载，也不能运行worker。

接收回执必须先由操作者对照总管的冻结Git对象与精确收件表生成到私有config；本机回执本身不构成审批来源。回执包含worker、accepted_frozen、source_commit、control_commit、完整runtime_sha256、精确argv、executable_sha256、数据库application_id/user_version。计划绑定回执SHA256、最终candidate SHA、release、环境路径及独立cwd；全局网站/共享依赖继续由现有build-binding准入证明，不关闭旧77/8或获批例外校验。

启动检查：冻结回执/文件字节/argv/二进制一致；仅本worker源码/编译/schema路径；唯一DB路径、0600、非软硬链接，**只读检查本worker库**完整性及域/版本。缺库或迁移不匹配即拒绝，不在serve/readiness自动DDL。只继承明确私密env，不继承宿主环境；拒绝provider密钥、旧密钥文件、代理、NEXT_PUBLIC、有效配置里的外网目的地址；允许原受控loopback方向。代码里未启用的URL常量不作网络行为证据。

Hunter要求外采=0、v2模式、ikun-main、v2-event、loopback/独立DB；Tracking要求remote_enabled=false、dedicated_account=false、token_file/service_token_file为空，服务方向令牌只取私密env。启动目录及release/worker/Python目录都不能存在.env/.env.local，防止Settings.load隐式复用配置。具体字段/CLI仍须与最终冻结实现核对，不能用协议快照替代冻结代码。

```sh
# PLAN为0600私有计划JSON；PENDING计划可render审查，但check/run必拒绝。
/Users/lvlei/.local/bin/python3.11 release-integration/scripts/night_worker_ops.py render --plan "$PLAN" --output "$NEW_PLAN_DIRECTORY"
/Users/lvlei/.local/bin/python3.11 release-integration/scripts/night_worker_ops.py check --plan "$PLAN"
```

接受冻结的实际运行计划必须render到新根plans子目录；launchd包装器使用固定C0生产Python。检查通过也只证明配置/字节/本库兼容，不证明真实来源或远端恢复。此准备阶段不安装、不启动、不迁移、不生成真实服务凭据。

## 每个模块的实际接入顺序

1. 收冻结SHA、审查control、全部依赖/SQL/lock/源文件与正式入口映射hash、P0/DEC证据；固定Git对象，核对冲突而非重写业务。Projects认证500/C03修复也须先接获验收冻结的确切依赖。
2. 按准入表最小扩展BFF/controller/runtime/readiness与模块页面，保留Auth10、只读主页及现有用户数据。单个worker不可用不拖垮网站Auth/Projects readiness；模块显示未接入/未连接，不把本地idle/夹具connected当真实来源。
3. 在唯一heavy lock里生产build和实际Next start回归；对应本地worker链、权限/SSE撤销、数据库互不影响、显式迁移/备份/恢复均通过，绑定最终集成SHA/BUILD_ID与各worker完整产物。
4. 在线备份既有库。只按冻结入口显式初始化/迁移本worker自己的库，缺少兼容/恢复证据不自动降级。使用现有upgrade_c0_lite.py更新网站；新worker另render/preflight，确认新label归属、端口空闲、私密目录、服务方向凭据后才bootstrap。
5. 检查每个job单实例、外采关闭、实际transport零外联/无provider调用、本地任务重启恢复。夹具必须标“本地验收夹具”，页面固定如实提示“未连接真实来源”。上线回执分别记录网站与各worker运行SHA，不把未更新的另一个job写成已升级。
6. 公网同源页面/BFF/角色/四方法403/静默SSE撤销验收；仅恢复已授权合成账号，完成或阻断都禁用，真实admin不动。出具逐模块回执后继续等待另一个冻结模块。

## 回滚

网站继续用现有upgrade工具自动回滚代码/config/plist/owner，保留live DB。新worker失败只卸载该精确job，保留数据库和日志，页面回到未连接。

```sh
/Users/lvlei/.local/bin/python3.11 release-integration/scripts/night_worker_ops.py unload --plan "$OWNED_RUNTIME_PLAN"
```

unload只接受新根plans内的私有计划，逐字核对已安装plist的label、argv与cwd，拒绝未知同名作业；只bootout该label并将其plist移到新根rollbacks，避免下次登录自动复起，数据库不删不覆写。它不要求坏库仍健康，故故障时仍可执行。该动作已有夜间新worker回滚授权，不涉及旧服务。准备测试只mock launchctl，没有执行真实卸载。

恢复旧worker代码前必须有schema向后兼容证据；否则只停该新模块并保留现场，按冻结恢复方案备份到新路径验收。不能覆盖在线库或用broad pkill/global supervisor stop。

main、正式ikun.ca、真实6551/第三方REST/付费、下线旧版、已有Cloudflare/旧作业、共享Watch继续受保护。B3冻结后语音才由全站UI自有新目录交付，集成只收验收冻结addon，不自行开发第二套信息流/播报。

已验收小依赖：Projects认证构造器修复 `cc95dc27852d056457ca0582cff64a88c0eab1d4`，精确helper源hash见intake.json。仅登记供下个已验worker收件，不为此单独构建/部署；C03及B3/B4核心仍待各自最终验收冻结。
