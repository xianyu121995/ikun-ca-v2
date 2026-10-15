> 历史交接：当前最终 HTML 基准、活跃入口和验收结果请以 `apps/website/features/homepage/FINAL_HANDOFF.md` 为准。

# 主页 UI 候选交接 · v2 foundation-v0.1.0

本模块仅负责主页视觉与浏览器交互原型。Worktree：`ikun-ca-v2-worktrees/homepage-ui`，分支：`codex/homepage-ui`，基线：`f89d8f55fc3e68d6360e7a1e33e23bde48591098`。

## 当前状态

主页 UI 候选可独立点击测试；真实功能与全站公共组件**尚未接入**。公共 UI 门禁为 `PENDING_SHARED_UI`，功能接口门禁为 `PENDING_PROJECTS_OWNER`。不作为 READY 或部署证据。

保留此前独立原型目录原状。此候选仅迁入本窗口新写的主页代码，不包含旧站 Navigation/Modal/CSS 快照、旧配置、旧业务实现、旧 DB、账号或 node_modules。当前依赖是本 Worktree 通过 `pnpm install --frozen-lockfile` 独立安装。

## 页面与范围

新增 `/prototypes/homepage`，原有 `/`、layout、全站 globals、BFF、health、worker、schemas、contracts、runtime、根依赖及锁文件均不修改。

页面仅在 `IKUN_HOMEPAGE_UI_PREVIEW=1` 且 `IKUN_ENV!=production` 时可访问；默认关闭，生产环境即使设置预览 flag 也返回 404。它是同一 Next.js 网站内的路由，没有新增正式服务。

14 个虚构 fixtures：12 个“正在做”，2 个“已移除”。顶部、每行、详情及编辑窗口均标记演示。存储键为 `ikun:v2:homepage-ui:demo:v1`，不读旧原型或旧站键。`.example` 只显示占位提示。

表格展示项目名称/分类、评分、发现日期、官网、简介、进度、备注/下一步。支持搜索、组合筛选、列头/下拉排序、行高、查看、编辑、添加、多选移除、撤销、恢复、确认删除、空状态、损坏存储恢复、刷新保留和跨标签页同步。

`user/superadmin` 切换只是明确标记的**界面权限演示**，不创建 session，不调用认证、不代表已登录或通过服务端鉴权。只读模式禁止演示写入并清除此前的撤销/编辑操作。正式权限必须由认证/BFF 验证，不信任浏览器 role 或按钮状态。

## 全站公共 UI 接入

截至本次候选交付，基础提交及可见的全站 UI Worktree 没有正式公共组件。没有写 `packages/*`，也没有另建全站共享体系。

`ui-port.tsx` 定义 Button/Input/Select/Textarea/Badge/Dialog 接入点，业务组件统一通过这些端口渲染。实际主页必须显式注入正式组件；缺少 Provider 会抛出错误。`previewUI` 为本候选新写的原生演示控件，仅由预览入口显式注入。正式集成时由全站 UI owner 提供 adapter、壳层与 tokens；不要直接把 previewUI 当作正式公共组件。

核心组件必须显式传入 `store`，没有默认演示 fallback。`preview.tsx` 是唯一注入 demoStore 的入口。图标为本模块简单 SVG，未添加 lucide 或其他运行依赖；正式统一图标同样交全站 UI owner 接入。

## 接口/字段差异（提请总管及项目 owner 审阅）

以下是 UI ViewModel，未修改共享契约，也未实现项目 CRUD 或 BFF。

| UI 候选 | 现有 v1 契约 | 接入要求 |
|---|---|---|
| `id` 为 demo fixture/浏览器 UUID | canonical `project_id=prj_<UUID v4>` | 真实模式只使用项目领域返回的 ID；不要把演示 ID 发到 API |
| `name`、grade、发现日期、官网、简介、category、stage、progress、notes | ProjectSummary 目前仅 project_id/name/status/revision/updated_at | 评分等字段由 projects owner 提交正式 DTO 扩展供总管审阅；不能从 raw Hunter 数据补字段 |
| camelCase `discoveredOn`，北京时间日历日 | API snake_case，UTC ISO 8601 | 显示层转换日期；真实发现时间的来源和可编辑权限需 owner 明确 |
| `membership=active/removed` | 项目 `status=active/archived` | 主页移除只取消主页成员资格，不等同项目归档；具体持久字段/端点待批准 |
| 演示删除从浏览器列表清除 | DELETE 归档 tombstone，保留审计/事件引用 | 正式删除按钮改为确认归档并显示服务端结果；禁止物理删除 DB/监控历史 |
| 完整内存列表搜索/筛选/排序 | cursor/limit/status，排序约定 `(updated_at,id)` | 真实筛选/排序参数需 owner 确认；不能仅筛当前页却显示为全量结果 |
| 同步 HomepageProjectStore | 异步 API、request_id、错误、revision/ETag | 改为异步提交，补保存中/失败/无权限/冲突；收到真实确认后才提示成功 |
| 本地 revision，原型重置/撤销 | 写 Idempotency-Key；PATCH/DELETE If-Match | 真实写入遵循契约，错误/unknown 不盲重试；重置演示只留测试入口 |

UI 的 `readOnly` 只是展示状态，必须从可信认证结果派生。数据源只接授权白名单 DTO；不要接 raw 事件、猎手身份、账号列表或跨库 SQL。遇到真实接口错误显示错误/不可用，不能静默退回 fixtures。

## 运行与验证

在本 Worktree 根目录：

```sh
export PATH="/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH"
pnpm install --frozen-lockfile
pnpm build:shared
IKUN_HOMEPAGE_UI_PREVIEW=1 pnpm dev:website
```

访问 `http://127.0.0.1:3700/prototypes/homepage`。不需要启动 hunter/tracking 服务，不调用 health/ready 或创建业务 DB。

构建/类型检查：`pnpm --filter @ikun/website build`、`pnpm --filter @ikun/website typecheck`。构建串行，沿用基础 cpus=1 与 heap 配置。

浏览器 QA 工具仅安装到本模块忽略的 `.tools`，不修改 workspace 依赖或锁文件：

```sh
npm install --prefix apps/website/components/homepage-ui/.tools --no-save --package-lock=false --ignore-scripts --no-audit --no-fund @playwright/test@1.64.0
PROTOTYPE_CHROMIUM=/absolute/path/to/chromium node apps/website/components/homepage-ui/.tools/node_modules/@playwright/test/cli.js test --config apps/website/components/homepage-ui/playwright.config.cjs
```

验收覆盖 10 个浏览器场景、1440/1680/2560px、390px 手机、详情/编辑/删除截图及只读模式。机器已有 Chromium，可通过上述变量指定；本窗口未下载浏览器。

证据见 `evidence/test-results.json` 和 `evidence/verification.json`。未验证真实登录、项目 API 持久化、数据库、采集、Watch、生产部署和正式全站 UI。提交只包含原型路由和本模块；由总管审阅后合并，无需本窗口修改共享规范或部署。
