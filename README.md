# ikun.ca v2

当前阶段：**phase2-v1.0.0 规范冻结**。[统一规范](docs/phase2/README.md) · [放行和验收](docs/phase2/RELEASES.md)。9个v2候选已安全提交；只放行4个独立UI窗口，其余新工作、合并与生产部署暂停。规范提交没有合并业务或修改运行门禁。

全新 TypeScript/pnpm 单仓库；三个独立服务、三个物理业务数据库与独立 auth.db。当前交付工程骨架，不包含业务实现、旧版迁移或生产部署。

| 服务 | 目录 | 默认地址 | 拥有的数据库 |
|---|---|---|---|
| Next.js 网站/BFF | apps/website | 127.0.0.1:3100 | projects/projects.db、auth/auth.db |
| hunter-worker | services/hunter-worker | 127.0.0.1:3111 | hunter/hunter.db |
| tracking-worker | services/tracking-worker | 127.0.0.1:3112 | tracking/tracking.db |

## 本机运行

在本仓库根目录运行；需 Node 24.22.0、pnpm 10.33.1。此次基础交付的本机 Node 安装在忽略目录 `.tools/node`，不更改全局 Node。其他 Worktree 可共用这个只读二进制，依赖和数据必须分开。

```sh
export PATH="$PWD/.tools/node/bin:$PATH"
cp .env.example .env.local
pnpm install --frozen-lockfile
pnpm build
pnpm typecheck
pnpm test
pnpm smoke
```

三个终端分别启动；开发启动前至少完成一次 `pnpm build:shared`：

```sh
pnpm dev:website
pnpm dev:hunter
pnpm dev:tracking
```

构建后的三个独立运行命令：

```sh
pnpm start:website
pnpm start:hunter
pnpm start:tracking
```

`/health/live` 是进程存活；`/health/ready` 是本服务存储可用。worker 为 idle、external_io_enabled=false。内部 `/internal/v1/status` 需要本地配置的至少 32 字符 token。公开业务 API 返回 503 AUTH_NOT_CONFIGURED；配置内部鉴权后的业务接口返回 501 NOT_IMPLEMENTED。

SQLite 文件在本 Worktree 的 `var/dev` 下首次 readiness/worker 启动时创建。build/test/smoke 不读取旧库；测试只使用临时数据库。依赖安装需网络；基础运行不调用任何外部平台。

开发窗口入口：[AGENTS.md](AGENTS.md)、[交接规范](docs/HANDOFF.md)、[架构](docs/ARCHITECTURE.md)、[API](docs/API.md)、[所有权](docs/OWNERSHIP.md)、[生产方案](docs/DEPLOYMENT.md)。
