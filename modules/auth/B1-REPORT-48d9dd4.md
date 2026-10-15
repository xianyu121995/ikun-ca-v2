# 登录系统 B1 本地交付 · 2026-10-15

结论：**本地 B1 验收 PASS，待总管审查具体新 SHA。未接入主站、未合并、未推送、未部署；不自动放行后续业务。** 早期 FREEZE.md 的失败记录完整保留，本报告仅描述本轮新证据。

## 来源和范围

| 项目 | 固定值 |
|---|---|
| Worktree / 分支 | ikun-ca-v2-worktrees/auth / codex/auth |
| 认证原冻结 | aa3cf65ce5c24cc293e0daec279659d2cc080c5f |
| P0 独立安全修复 | 8f381a0b07253d57683e0078dbc33369cad7ab69 |
| 规范 | phase2-v1.0.0 / 9699375c920465b5d802e7acff17b5421203e544 |
| B0 基础 | b0-accepted-v1.0.0 / 85be3bd6dce25d82033b6cb1a7157aaa39bd571e |
| 公共 UI 来源 | 486294ac3255b08fdb13a307ee15f96c571020d9 |
| 用户放行记录 | 2949d55f13e7669ea0ea2f139209ccf9cec73abb；docs/b1/release.json |

全部新提交仅 `modules/auth/**` 与 `schemas/auth/**`。`apps/website`、共享包/根锁、其他 Worktree、worker、旧版服务、Watch/Tunnel 和生产库未修改。所有接线候选留在 `modules/auth/integration/`，预览只从固定 Git 对象导出到 ignored 新目录，不覆盖原预览、残留或冻结提交。

最终 SHA 使用本分支 `git rev-parse HEAD` 查询；完成提交后的 `test-results/b1-final-receipt.json` 绑定完整 SHA、测试日志/浏览器/构建文件 hash、源码 hash 与 Git 状态，避免文档自引用 SHA。该回执为本地忽略产物，不含账号库或凭据。

## 验收逐项

| 门槛 | 实际结果 |
|---|---|
| 密码 P0 | 3 个静态表单和生成页面均显式固定同源 POST；新增 2 项 Node 回归。真实 Next/Chromium 对每个表单各执行 JS disabled、脚本未绑定，共 6 组：实际导航 POST，415 安全拒绝；请求 URL、CDP 浏览历史、Next 日志和响应均无虚构密码 |
| 原最终回归 | 原 33 项完整保留并按新契约调整预期；加 P0 2 项、B1 24 项，**59/59 通过，0 skipped/failed/cancelled**，最新耗时约 26.7 秒。未引用早期 31 项/Python 成绩 |
| Next | 固定 B0 + 固定 UI + 本模块候选；独立离线 frozen install；contracts/runtime/UI/Next 串行构建通过。实际静态页消费固定 UI 与 CSS 已检查；不是未使用的依赖声明 |
| 浏览器 | 1440×1000 与 390×844；登录、用户名/密码字段、首次改密后重新认证、创建/禁用/启用/重置、退出及普通用户拒绝均通过。原失败的 **390px 重置动作实际完成**。键盘 Shift+Tab/Tab 循环、默认取消焦点、Esc 取消通过；page errors 0 |
| 初始管理员 | 真实 CLI 伪终端双次隐藏输入初始化通过，无密码回显；重复初始化/管道拒绝有 Node 回归；无默认账号或公开注册 |
| DTO | AuthSessionV2 完整且 capabilities 服务端计算；user/强制改密管理员能力全 false。AuthUserV2 为 user_id，无 id/hash/token。用户查询 PageV2，默认50/最大100，cursor 绑定 actor/scope/query/limit 并校验 HMAC。reset-password 仅 new_password；PATCH enabled/role/must_change_password 非空白名单；logout 返回 logged_out；改密返回 changed/reauthentication_required 并清 Cookie |
| 可信身份/业务门 | 固定 ikun-main，仅 superadmin/user。身份来自当前 auth.db 会话，不采纳客户端 role/user/scope；跨 scope query/header 拒绝。AuthHttp.business 在调用 handler 前验证身份/权限/CSRF，返回冻结的 AuthPrincipal；未认证或 user 写请求不调用业务回调。未代写真实业务 handler |
| 会话/权限 | 禁用、重置、本人改密、降级、强制改密状态修改撤销会话；最后管理员并发禁用/降级保护。Cookie/Host/Origin/CSRF、限流/重启、版本/幂等回放均有完整回归 |
| SSE | BFF 包装器自动包装 SSE；建连/每块数据/静默每秒复验。禁用、重置、改密、降级、过期、数据库不可用的静默撤销和上游取消全部通过；块发送前撤销不泄露后续数据 |
| 单库/兼容 | 仅 auth/auth.db。新库、foundation1→002、冻结 Auth2→新 registry、重启/重复迁移、错 checksum、scope/future version 拒绝通过。冻结用户/hash/session/幂等回执/legacy checksum/metadata额外列原样保留；失败事务回滚并保留冲突数据，备份恢复到新路径通过 |
| B0 版本准入 | 实际固定 B0 默认 maximumVersion=1 拒绝 Auth2；预览显式 names=[auth]/maximumVersion=2，再做 Auth 领域 checksum/scope/结构验证。3 次真实 HTTP readiness 返回200，前后 schema/版本/registry完全一致，不执行 DDL；缺库/版本1只读检查不创建/迁移 |
| 边界 | 浏览器临时 DATA_ROOT 实际只有 auth 目录，业务库数量0；测试服务正常退出并清理其临时数据。源码和验证均未访问生产、provider 或真实凭据 |

## 实际命令与产物

在本 Auth Worktree，Node 为既有只读工具链的 24.22.0；没有修改主目录工具链或依赖版本。

```sh
node modules/auth/scripts/generate-schema.mjs
node modules/auth/scripts/generate-ui.mjs
pnpm exec tsc -p modules/auth/tsconfig.json
node --test modules/auth/tests/*.test.mjs
node --check modules/auth/static/auth.js
node modules/auth/scripts/prepare-preview.mjs
node modules/auth/scripts/build-preview.mjs
IKUN_NODE="$(command -v node)" IKUN_TEST_CHROMIUM="<本机已有Chromium可执行路径>" \
  modules/auth/.venv/bin/python modules/auth/tests/browser_smoke.py
```

独立预览脚本使用本模块私有 package cache 进行 offline/frozen/ignore-scripts 安装，未写主目录 cache。浏览器脚本的 Python 仅为测试驱动，不是新增正式服务。

本地证据均在 `modules/auth/test-results/`：

- `b1-final-regression.log`：59 项完整输出。
- `b1-build.log`、`b1-build.json`、`b1-preview.json`：串行构建、固定 SHA、锁 hash、全部运行源码输入 hash。
- `b1-browser-result.json`：成功结果、6 项密码 fallback、keyboard/mobile/readiness、实际 UI/code hash。
- `b1-browser-1792061714530/`：最终成功的桌面/手机/重置弹窗截图、Next 日志、浏览器 JSON。
- 早期失败预览/日志仍保留，首次键盘焦点失败经本轮显式焦点循环修复后复验通过。

Git 白名单、秘密检查、diff --check 与原 pre-commit hook 必须正常通过后提交。最终结果及完整 SHA 记录在上述最终回执。

## 总管后续收件补丁清单（本轮没有执行）

1. 主构建在网站前生成/验证 Auth schema/UI 并编译 module；运行产物无需 Git 或 Python。正式安装依赖/根锁仍由总管审阅，不从其他 Worktree symlink node_modules。
2. 审阅 `integration/website` 中专属认证路由；root proxy 仍归总管，不能整份覆盖。保留固定只读 API 清单，未知 GET 与 Hunter 账号配置不授予普通用户。不要把角色/用户字段从客户端头注入为可信上下文。
3. 主站 readiness 明确仅对 auth 准入2，且调用领域校验；本轮 `integration/preview-only/lib/stores.ts` 仅为 Auth2 夹具，不可直接替换涉及 Projects IPC 的正式 readiness。
4. Projects/Hunter/Tracking BFF 在其各自放行批次接 `AuthHttp.business`/可信 principal；SSE 必须持续撤销，不只依赖 proxy 建连校验。跨进程方向凭据/IPC 的身份信任由 B2 及后续领域验收，本轮未接真实域。
5. 正式 UI 组合仍消费唯一冻结公共包；本模块密码相关展示沿用 phase2 tokens，未改公共组件。全站入口、真实路由组合、TLS/Cloudflare、外部网络/平台与生产账号单独验收。

## 剩余阻断与未验证

本地 B1 所列门槛无已知未通过项；**总管仍须核验最终 SHA 后记录 B1 接受**。真实业务链路、跨进程 handler、四库组合、Cloudflare/公网登录、生产负载/备份恢复和部署未执行，不能用本报告替代 C0/D0。B2/B3/B4/C0/D0 没有因此获准启动。禁止擅自合并、推送、部署或清理其他窗口现场。
