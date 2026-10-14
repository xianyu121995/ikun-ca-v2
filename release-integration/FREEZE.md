# 集成验收已有成果冻结 · 2026-10-15

状态：**工具与基础环境验证已冻结；全站业务验收 BLOCKED，未上线。** 根据第二阶段收尾要求，仅安全提交已有成果，不再新增开发、硬化、业务接线、接口调整、分支合并或远端/部署测试。正式 API、权限和所有权规范等待总管另行放行。

## 基线与提交

- Worktree：`/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration`
- 分支：`codex/integration`
- 原基线：`f89d8f55fc3e68d6360e7a1e33e23bde48591098`，tag `foundation-v0.1.0`
- 本次只提交 `release-integration/` 中自己的工具、脱敏证据、模板、测试及文档，不改共享源码、锁文件、其他窗口文件或主目录。

冻结提交的完整 SHA 查询：

```sh
git log -1 --format=%H -- release-integration/FREEZE.md
git status --short --branch
```

自引用提交 SHA 不写进提交本身；提交后的完整 SHA 和最终状态通过聊天交付。未提交的本地配置和运行数据不属于冻结源码。

## 已有范围

`scripts/release_ops.py` 提供固定提交/验收报告哈希校验、隔离合并工具、四库物理路径检查、launchd 计划生成、正式启动批准记录校验、SQLite 在线备份与只恢复到新目录的演练。没有执行业务分支合并或正式发布。

`prepare_config.py`、`audit_environment.py`、`snapshot_interfaces.py` 生成独立配置和只读脱敏基线；`launchd_drill.py` 与 `foundation_launchd_check.py` 保存本地原生验证工具。Cloudflare 文件仅为占位模板；操作单与验收矩阵见 `docs/`。

原始探索副本仍保留在 `/Users/lvlei/Documents/ChatGPT/ikun.ca开发/release-integration`，不再写入、不纳入这次提交。当前 Worktree 中的版本是此次冻结交付。

## 已有验证结果与限度

| 项目 | 已记录结果 | 范围与证据 |
|---|---|---|
| 工具单元测试 | 32 passed、0 failed、0 errors | `evidence/tooling-tests.json`，包括文件隔离、跨库删除 fixture、WAL备份恢复、正式启动限制、收件与隔离合并；不是业务全流程 |
| 基础构建/类型检查 | 通过 | `evidence/foundation-build.json`，独立 Worktree、锁定依赖、Next.js正式构建 |
| 基础测试/smoke | 5 passed；smoke通过 | 同上；idle基础服务、四库、鉴权门禁及独立重启，不证明登录/真实监控 |
| 原生 launchd fixture | 非 Documents 路径演练通过，任务已卸载 | `evidence/launchd-fixture-drill-outside-documents.json` |
| 原生真实基础构建 | 最终 PASS，三个任务全部卸载 | `evidence/foundation-native-launchd-final.json`：Next.js+两个编译worker、四库、各服务崩溃恢复、备份恢复；仍是idle foundation |
| Cloudflare模板 | ingress语法与匹配检查通过 | 只证明模板语法/匹配；未加载到线上Tunnel，未验证真实凭据或新源站 |
| 模块收件 | 历史快照为1/6、BLOCKED | `evidence/module-intake.json`，检查时间为上海2026-10-15 05:48；不是各分支之后交付状态的实时声明 |

32项单元测试执行后，两个原生演练脚本修改了清理等待逻辑；`tooling-tests.json` 中这两个脚本的哈希因此早于冻结版本。修订后的 `foundation_launchd_check.py` 与 `launchd_drill.py` 的等待函数已由最终原生演练实际验证。冻结阶段不重跑完整测试，也不把旧单元测试记录冒充冻结版本全量测试。

失败记录原样保留：

- 初次 fixture 从 Documents 启动被 macOS拒绝，日志为 Operation not permitted；对应 `launchd-fixture-drill.json` 不作为通过证据。改到 `/private/tmp` 后的已有复测通过。
- 首次真实基础构建报告为 `FAIL_CLEANUP`，因为 `bootout` 后立即查询的记录尚未消失；对应 `foundation-native-launchd.json` 保留。随后已有修订采用有界等待，最终报告为PASS且三个任务已卸载。
- 一次本机Python编译检查因默认缓存目录权限失败；改用 `/private/tmp` 缓存后的已有检查通过。一次打包检查因无依赖 workspace 不存在 node_modules 而停止，之后的已有修订验证通过。这些不是自动审批拒绝。

## 未验证与发布阻断

- 未完成最终业务合并及猎手发现→人工加入→NEW_TWEET→正式主页展示的组合验收。
- 登录/两种角色/统一认证存储、业务库实际删除隔离、项目与worker迁移归属、跨模块DTO/receipt的最终兼容尚未组合验证。
- 未做真实6551账号、配额、Watch隔离、实时推文或真实任务恢复验证；未改共享Watch。
- 原生证据仅证明基础进程/数据库恢复，不证明业务连接、持久任务reconcile或最终负载下恢复。未做30分钟业务负载及8GB资源压力验收。
- 正式launchd安装、无人登录/机器重启/FileVault恢复、日志轮转、定时及离机备份、正式域名切换和线上回滚均未执行。
- 公网只读HEAD曾分别得到curl302 Access登录跳转与Python客户端403；不能据此声称新源站已发布或真实登录可用。

未正式发布、未切换域名、未停止旧服务、未覆盖旧版数据库/脚本/共享配置。不在未通过全站验收时请求发布批准。

## 残留文件与停止边界

保留本 Worktree 的忽略文件：`.env.local`、独立 `node_modules/`、`.pnpm-store/`、编译 `dist/`、网站 `.next/`/tsbuildinfo，以及 `release-integration/config/accepted-modules.local.json`。不提交、不覆盖、不清理这些文件。

原生演练在 `/private/tmp/ikun-v2-foundation-*/` 和 `/private/tmp/ikun-ca-v2-launchd-*/` 的测试构建、数据库、配置、日志与备份保留现场；完整最终运行路径见相应JSON证据。相关测试launchd任务已卸载。系统Python的临时编译缓存也保留。它们不属于正式环境或Git交付。

后续仅在总管放行正式规范后继续集成；发布、域名切换与停止旧版服务仍各自需要用户明确批准。本次不通过工具向其他聊天回信。
