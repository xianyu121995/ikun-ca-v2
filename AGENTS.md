# ikun.ca v2 开发规范（所有窗口必须遵守）

本仓库是全新工程。只开发被分配模块，不复制旧版代码、数据库、配置、账号列表或运行数据。基础阶段不实现业务监控、交易、登录、项目 CRUD 或第三方 Watch 调用。

## 开工前

1. 阅读 `docs/HANDOFF.md`、`docs/ARCHITECTURE.md`、`docs/API.md`、`docs/OWNERSHIP.md`。
2. 确认 `git rev-parse --show-toplevel` 指向自己的 v2 Worktree，`git branch --show-current` 是分配分支。
3. 使用 `.node-version` 指定 Node 24 LTS，`pnpm install --frozen-lockfile`。每个 Worktree 独立 `.env.local`、`node_modules`、`var`、端口。
4. 主工作目录由技术总管持有。不得在其他窗口的分支、目录、数据库中修改或运行任务。

## 代码与数据边界

- 网站/UI 窗口：`apps/website` 的已分配页面与 BFF；project/auth 业务分别由“再做项目管理”和“登录系统”窗口持有，UI 窗口不得代写。
- 猎手窗口：`services/hunter-worker`、`schemas/hunter`，只读写 hunter.db。
- 跟踪窗口：`services/tracking-worker`、`schemas/tracking`，只读写 tracking.db。
- 技术总管：仓库根文件、锁文件、`packages/contracts`、`packages/runtime`、接口规范、部署工具、认证/项目基础，负责合并。各 UI 窗口共享组件候选亦须审阅，不能同时覆盖共享文件。
- 跨模块只能调用 API。禁止跨库 SQL、ATTACH、直接读其他服务 DB/WAL、复制 raw payload 到网站。
- Hunter 身份、账号列表、原始事件永不进入公开项目 DTO、日志、历史或 SSE；共享契约必须显式列字段。
- 修改共享契约、依赖、数据库版本、权限或模块归属，先提交规范变更供总管审阅；在自己目录完成候选，不擅自修改其他窗口工作。

## 工程标准

- 遵循现有 TypeScript、async/await；最小可运行修改。每个错误有稳定 code、retryable、request_id。
- 重要状态持久化；Fetch → Parse → Filter → Deduplicate → Action → Verify → Store → Alert。
- 外部 I/O 必须 timeout、限流、并发上限；重试按 API 文档执行，指数退避和抖动。不能在不确定是否成功时重复付费/资金操作。
- 所有写入做身份/租户/权限校验、参数校验、幂等与 revision 校验；迁移只针对自己的新 DB。
- secrets 只放忽略的本地配置；不写日志、不放 NEXT_PUBLIC_*、不提交数据库/密钥/运行数据。
- 骨架 `ready` 只表示进程和存储可用。没有真实数据源心跳，不宣称 connected；没有真实验证，不宣称业务成功。
- 检查最新官方文档，不猜第三方 API。Web3 默认 dry-run，真实链上资金操作另需明确授权。
- 旧版服务、Cloudflare Tunnel、共享 6551 Watch、HunterRadar/AlphaPulse、生产数据均为禁止修改边界。只有用户明确批准后才可变更。

## 交付

在自己的分支提交，提供 commit SHA、修改文件、验证命令和结果、未验证项。由总管合并到 `codex/develop`，验收后再合并 `main`。不要直接 push main、部署或替其他窗口实现业务。不要因文档写了后续命令就自动执行部署。
