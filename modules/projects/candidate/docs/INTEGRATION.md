# 主站集成候选与兼容边界

日期：2026-10-15，模块分支 codex/projects，基线 f89d8f55fc3e68d6360e7a1e33e23bde48591098。

用户已明确分配主页项目 CRUD/独立 projects.db/受控加入/服务端权限/页面测试。本目录为该任务实现；其余模块的代码、数据库、运行服务均未修改。

开发开始时 V2 目录只有空 Git 元数据；期间总管在主目录生成了基础工程及 AGENTS/共享契约。本候选随后移到独立 Worktree。早期主仓库无提交时曾建立未出生的 codex/homepage-projects 候选，原目录保留。总管提供基础提交后，只复制自己的源码到指定 codex/projects Worktree 的 modules/projects/candidate；没有复制 DB、secrets、venv 或其他模块内容。正式交付提交建立在上述 foundation 基线，可以由总管合并到 codex/develop。

## 已完成和未完成

- 已完成：独立 projects.db、两次迁移、项目 CRUD、全部主页字段、真实查询/筛选/排序/分页、三段八列 UI、角色/租户校验、来源绑定、明确加入、持久映射/回执、幂等、tombstone、审计与隔离测试。
- 已匹配：canonical `prj_<UUID v4>`、projects application_id `0x494B0203`、不跨业务库 SQL、不采集、仅 loopback、无 raw/Hunter 身份 DTO。
- **未完成：主网站共享路由接线、正式 auth 会话接入、另一窗口新版 UI 的最终确认/接线、三个正式进程的组合验收、生产部署。**

## 需总管审阅的规范候选

根 AGENTS 要求“修改共享契约、依赖、数据库版本、权限或模块归属，先提交规范变更供总管审阅”；ARCHITECTURE 当前规定 TypeScript 单网站进程、不增加第四个服务。因此本候选不擅自编辑共享入口、packages、schema 基线或部署。以下是明确差异，不能把独立测试当作主站 READY。

| 事项 | 当前可运行候选 | V2 共同基线/集成工作 |
|---|---|---|
| 运行方式 | Python/FastAPI 独立本地验收 | 网站 Next.js 单进程；需总管决定把项目领域移植为 Node 模块，或审阅 Python 组件的进程方案 |
| 接口 | /api/home/*，JSON 直出，offset 分页 | /api/v1/* 与 /internal/v1/*，data envelope、cursor；需有版本化映射 |
| 角色 | 用户仅 superadmin/user；服务身份单独绑定来源与 tenant | 正式由 auth.db/BFF 验证 superadmin/user 会话；项目模块只接收可信服务端 identity，不读取 auth 库、不信任客户端角色头 |
| 版本控制 | expected_version、版本冲突 409 | If-Match / ETag / revision；需适配，不可静默改共享字段 |
| 幂等 | 新增 Idempotency-Key；导入固定 source/external_id，不覆盖人工字段 | 全部变更请求回执与统一 7 天保留、事件 hash 冲突规范需统一 |
| 删除 | 本库 soft delete，保留映射；不触发其他业务行为 | 本任务明确禁止删除上游记录；是否暂停订阅只能经后续单独授权的持久命令 |
| 内部加入 | 服务凭证绑定 source + tenant，explicit_add=true | 正式 event envelope、方向 token、统一 receipt DTO 需按总管确认版本适配；不能把普通采集事件直接当用户明确加入 |
| 迁移归属 | modules/projects/candidate/projects_service/migrations，自有 checksum ledger | 集成到 schemas/projects 前由总管分配编号和主库唯一 writer；不得两个迁移器同时启动 |

本次不实现通用监控事件 inbox/outbox、命令调度、SSE 或采集。受控加入不是后台自动采集入口。

## Next.js 入口候选

`integration/next-proxy.js` 是待审阅的 Next.js 16 opt-in 入口；未安装到 apps/website。未配置 PROJECTS_API_URL 时放行现有主页。配置后仅代理根主页、两份静态资源及 /api/home/*；仅连接固定 loopback 上游，身份 Cookie/Bearer/CSRF 交由项目服务校验，不打开任何 DB、不注入角色。

此文件已通过 JS 语法检查及临时 Next.js 16.4.1 + Chromium 同源验收：登录、角色拒绝、新增、刷新持久化、删除、退出均通过；只使用临时 projects.db。**未安装到正式主站，正式 auth 与最终 UI 仍未组合验收，不能作为正式已接线证据**。其启用需要总管同时确认进程方案、最终主页 UI 和账号系统衔接。网站已有 proxy/middleware 时应合并相应规则，不覆盖其他模块。

本地配置的审阅示例（不修改共享 .env）：

```text
PROJECTS_API_URL=http://127.0.0.1:8120
PROJECTS_PUBLIC_ORIGIN=http://127.0.0.1:3500
```

项目服务 PROJECTS_ORIGIN 必须与 PUBLIC_ORIGIN 相同；通过该入口使用同源 Cookie。Node fetch 会使用内部上游 Host，项目服务须额外配置 `PROJECTS_PROXY_AUTHORITY=127.0.0.1:8120`。该值只允许显式 loopback host:port；不接受外部 Host 或 X-Forwarded-* 作为身份，CSRF 仍要求公共 Origin。正式 HTTPS 需 PROJECTS_SECURE_COOKIE=1。生产入口切换、反向代理和 launchd 配置都未执行。

复现临时 Next 验收（从 candidate 目录执行，本 Worktree 需先 pnpm install --frozen-lockfile）：

```sh
PROJECTS_TEST_NODE=/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node .venv/bin/python integration/check_next_proxy.py
```

## 验收证据边界

测试只访问自己的临时 projects.db；有连接白名单测试和不透明 sentinel 文件摘要校验。没有读取/复制 hunter.db、tracking.db、监控库或其 WAL。默认本地开发库为空，截图的 Fixture 数据仅来自临时测试库。

合并前建议按顺序确定：正式 UI → 公共/内部 DTO 和正式 identity 接口 → 唯一迁移器/唯一 writer → 主站接线 → 同源账号/角色/租户/重启回归 → 由用户决定部署。无需为该审阅修改任何上游监控或共享 Watch。
