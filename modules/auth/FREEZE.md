# 认证模块已有成果冻结 · 2026-10-15

状态：**冻结候选 / NO-GO，上线与正式接入均未获验收。** 根据第二阶段收尾要求停止开发，只保存已有源码、测试、接口候选和证据；不继续修复、硬化或业务接线。

## 身份与边界

- Worktree：`/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/auth`。
- 分支：`codex/auth`。
- 原基线：`f89d8f55fc3e68d6360e7a1e33e23bde48591098`（foundation-v0.1.0）。
- 本次仅提交 `modules/auth/**`、`schemas/auth/README.md`、`schemas/auth/002_accounts.sql`。
- 未修改根依赖、锁文件、contracts/runtime、`apps/website`、worker、项目业务或三个业务数据库；未合并、推送、部署、重启线上服务或变更 Tunnel/Watch。
- 主目录此前的 `auth/` Python 候选、`modules/auth` 初期候选及其他窗口文件保持原状，没有清空、覆盖或替其提交。

## 已有实现

网站进程内 TypeScript 认证模块，Node 24.22 原生 Argon2id 与独立 `DATA_ROOT/auth/auth.db`，不增加正式服务。包含两角色登录/退出、初始管理员本机隐藏输入 CLI、用户创建/禁用/启用/重置密码、强制首次改密、会话过期/撤销、CSRF/Origin、持久限流、服务端权限门、账号管理幂等/版本校验、SSE 撤销包装器、登录/账号/用户管理 UI。

`integration/website/` 是可评审的 Next 路由/代理候选，仅在忽略的隔离预览中应用。正式网站没有接入这些文件；业务只读清单、SSE 消费者、TLS/Cloudflare 与完整业务权限链均待总管另行审核。协议细节见 README，不因候选存在而宣称已上线。

## 真实验证状态

| 检查 | 状态与限制 |
|---|---|
| 冻结依赖安装、`pnpm build:shared` | 认证 Worktree 独立依赖安装完成，共享库编译完成；无依赖版本变更 |
| TypeScript 模块编译 | 当前源已通过 `tsc -p modules/auth/tsconfig.json` |
| 后端权限测试 | 上一次执行 **31 passed / 0 failed**，约 19.7 秒；包含匿名/角色/写方法/CSRF/限流/撤销/并发最后管理员/迁移与 SSE。之后新增 2 项测试及若干已有收尾改动，**当前完整 33 项未复跑**，不得把旧结果当作最终代码全回归 |
| 隔离 Next 生产构建 | 最新 `next build --webpack` 已完成：编译、TypeScript、页面生成、构建追踪通过；仅在 `modules/auth/test-results/next-preview`，没有发布主站 |
| Next 浏览器 smoke | **失败/未完成**：初次发现代理相对重定向的 Invalid URL，修复后已走到用户管理流程；最近一次失败在移动端重置密码按钮可见性断言。已调整定位器等待，但尚未复验；无最终 browser-result.json，不得宣称整项通过 |
| 初始管理员 TTY | 最近一次 smoke 已执行真实 CLI 的伪终端初始化并通过不回显前置断言；整项浏览器测试失败，未做独立正式 CLI 验收 |
| 早期 Python 验证 | 曾有 35 个后端测试与 1 个浏览器流程通过；仅属主目录旧候选，**不能作为本次 TypeScript/Next 验收** |
| 生产/真实业务验收 | 未执行，未验证 |
| Git 路径/秘密检查 | 已运行仓库 `scripts/check-git.mjs`，`Git hygiene OK: 92 tracked files`；暂存清单仅含本模块与 auth schema，无 DB、venv、dist、截图或 secrets |
| `git diff --cached --check` | **未通过，退出码 2**：`.gitignore` 及 4 个 static HTML 的末尾新增空行。按冻结要求保留源码，不进行格式调整；未伪造通过。该检查不是仓库 pre-commit hook，提交时仍正常执行原 hook，不绕过 |

未新启动冻结后的测试。最新仍运行的既有构建已只读取其最终输出，确认退出码 0。

## 已知阻断，必须先审阅

1. **P0：含密码表单缺少显式 `method="post"`。** 当前 `static/login.html`、`password.html`、`users.html` 的表单依赖 JavaScript `preventDefault`；若脚本未加载/未绑定，浏览器原生默认 GET 可能把密码字段放入 URL、浏览器历史或访问日志。源码审阅已发现，**冻结要求下未继续修改或验证**。生成的 `src/ui.ts` 含相同表单。此项修复和无脚本回归前不得用于真实凭据或上线。
2. 最近一次真实 Next 浏览器 smoke 未通过；最后的定位器调整没有复验，移动布局是否存在实际问题仍须复查。
3. 最终新增/调整后完整后端测试没有复跑。README 描述的是实现与复现方式，不代表全部最终验收。
4. 正式接入文件、编译步骤、只读 API/页面清单及 SSE 包装器使用需要总管/业务 owner 审核。只校验 SSE 建连不等价于持续撤销。
5. `GET /api/auth/session` 为跟踪候选兼容适配，账号列表 DTO、会话轮换接口的幂等例外、固定 site scope 绑定及 002 迁移均需与新 API/权限规范一并审核；本窗口未修改共享契约。

## 残留与保存

- 所有源文件、测试及接入候选原样保留。
- 忽略的 `modules/auth/dist/`、`.venv/`、`test-results/next-preview/`、部分截图、`next-smoke.log` 保留本地，不进入提交。
- 没有最终浏览器成功 JSON；截图只证明相应页面曾生成，不证明完整流程通过。
- 失败 smoke 使用的临时 Next 子进程已在 finally 中终止，临时目录由 TemporaryDirectory 清理；未关闭其他窗口或生产进程。
- 秘密/路径检查、`git diff --check` 与提交回执见本次 Git 结果；回执写入忽略的 `test-results/freeze-receipt.json`，不产生自引用提交 SHA。
- 本次未遇自动审批拒绝；此前本地绑定端口和依赖安装均经工具批准。无尚待绕过或重试的审批动作。

## 查询冻结提交与现场

```sh
git rev-parse HEAD
git show --stat --oneline HEAD
git status --short
git diff HEAD^ HEAD -- modules/auth schemas/auth
```

仅在上述 Worktree 查询。后续新规范收到正式放行前，暂停新增业务工作。

## 2026-10-15 B1 后续记录

本文件上文完整保留 aa3cf65 的冻结时点失败与未验证状态，不能改写为当时已通过。用户后续通过 `docs/b1/release.json` 明确放行本地 B1。P0 安全修复单独提交 `8f381a0b07253d57683e0078dbc33369cad7ab69`；本轮完整证据、剩余边界与最终 SHA 查询见 `B1-REPORT.md` 和忽略的 B1 回执。不自动放行其他后端、合并或生产。

## 最终需求修订

用户后续明确放行在原 Worktree 修订 B1；以最后确认指令取代旧管理后台需求。
原 `48d9dd4` 与本文件的旧失败/通过记录均保留历史语义。新方案移除网页账号管理，改为本机CLI，7天绝对会话，本人改密安全建立新会话，实际复用公共UI。最终交接见新的 B1-REPORT.md 和 INTEGRATION.md；仅本地开发/测试/提交获准，不合并或部署。
