# 主页 UI0 交接 · phase2-v1.0.0

规范：`9699375c920465b5d802e7acff17b5421203e544` / `phase2-spec-v1.0.0`。原候选 `eed9434fb73bba6e71e2040d2db43bf2632f650a` 原样保留在历史；本次新增 phase2 视图，不 amend/reset/rebase/merge/cherry-pick。冻结规范文件 SHA256 位于本目录 `spec-pin.json`。

当前范围仅 UI0：页面展示、纯 DTO 视图、props/callback 和隔离浏览器验证。B0/真实领域接线/集成/发布未放行，本交付不表示 READY 或正式功能验收。

## 文件与入口

- `features/homepage/types.ts`：本页 phase2 展示声明，与冻结 DTO 逐字段对应；尚不 import 未传播的共享 types。
- `features/homepage/view-model.ts`：字段白名单、安全 URL、北京时间展示、null/ID/page 检查，无 I/O 或 ID 生成。
- `features/homepage/demo-fixtures.ts`：仅演示用，12 个虚构项目（active 10、hidden 1、removed 1），全部使用 demo-* 键。
- `components/homepage-ui/phase2-homepage.tsx` / `.css`：纯页面；通过 props 接收数据、能力与回调，不持久化、不请求 API。
- `components/homepage-ui/phase2-preview.tsx`：明确标记的 demo 控制台与模拟回调；500ms/250ms 计时仅在此演示宿主。
- `app/prototypes/homepage/page.tsx`：仍需 `IKUN_HOMEPAGE_UI_PREVIEW=1`，生产环境禁止。未改 root page/layout/globals/BFF/DB 或 worker。

上一版 component/model/测试与证据保留为历史候选；当前路由使用 phase2 入口。旧版 `HANDOFF.md` 和 10 项结果不代表本轮验证。

## DTO 与视图规则

| 输入 | UI0 展示 / 回调 |
|---|---|
| `project_id` | 直接作为稳定 rowKey；live 检查 canonical 格式，拒绝 demo/名字/URL；不生成项目 ID |
| `rating` | S/A/B/C/D/null，null 为“未评分”；query 使用 unrated，写入保持 null |
| `progress_stage` | todo/researching/watching/participating/completed/paused 六种中文阶段 |
| `progress_percent` | null 为“未知”且不画进度条；0 明确显示 0%，不根据阶段或评级推算 |
| `home_membership` | hidden/active/removed，和进度分开；切换列表只触发查询回调 |
| `discovered_at` | 原 UTC 保留；Z/+00:00 的已知时间显示北京时间；null/无效值显示未知；表单只读 |
| `token_date/status` | 日期保持 YYYY-MM-DD，不转时间戳；null/unconfirmed，已知日期 confirmed/estimated |
| `website_url` | 仅 http(s)，拒绝 URL 凭据和脚本协议；空值为未提供；React 渲染纯文本 |
| `name/category/description/notes` | 120/80/4000/4000 字符，category 可 null，不强制营销类别 |
| `revision/created_at/updated_at` | 来自输入，只读；写回调 target 仅 project_id/revision，fields 不含这些元字段 |
| 额外 raw/身份字段 | 纯投影不保留 raw_payload、猎手归因或未知键，不透传原始记录 |

一页最多 100 条且 ID 唯一；缺字段或无效 live ID 显示公开 VALIDATION_ERROR，不构造占位 canonical ID。筛选/排序明确只作用于当前页；`onQueryChange`/`onNextPage` 通知拥有 cursor 的领域适配器，UI 不把 cursor 当 checkpoint，也不把一页结果宣称全量。

固定 scope 文案为 `ikun-main`。浏览器不注入 actor/role/tenant 头或实现鉴权。`context.mode` 必须显式给出；live 默认能力 false，只有可信 role=superadmin 且 can_edit_projects=true 才呈现可执行写操作。普通 user 保留读，按钮原因可见。真实服务端必须再次校验。

## 回调协议

`Phase2Homepage` 接收 `context/data/callbacks/query?`。数据和操作结果均由接入方提供；没有 demo fallback、内部 fetch、SQLite、SSE、轮询或持久任务。

- `onCreate(fields)`、`onUpdate({project_id,revision},fields)`：仅标准 ProjectFields 投影。
- `onMembership(target, add/remove)`：明确加入或移出主页。
- `onDelete(target)`：phase2 DELETE 仅变 removed，资料/ID/审计/监控引用保留。确认文案说明监控状态保持原样。
- `onQueryChange(query)`、`onNextPage(cursor)`、`onReload()`：只读查询意图。
- `onReconcile(operation)`：单独核对原结果，不能偷偷重发写入。

写回调返回 `OperationResult`：state、公开 request_id、可选原 command_id/error。accepted/pending/running 展示等待，unknown/超时展示“结果待核实”，不当作成功、不提供重复写按钮。Promise 在途禁用提交/关闭/Esc，通过 ref 阻止同一 tick 连续提交。只有回调明确 succeeded 才关闭写窗口；数据更新仍由 props 提供。409 阻止原表单重复提交，提示重新读取；任意 thrown Error 转公开 INTERNAL_ERROR/unknown，不展示私有原文/stack。

状态转换仅用于呈现，不实现命令引擎、幂等库、ETag/CSRF/会话/重试或 RPC。领域 adapter 后续必须按冻结 API 处理 Idempotency-Key、If-Match、权限、scope、回执与 cursor；本 UI 不自造这些真实业务证据。

## 公共组件接入

主页现已直接 import 唯一 `@ikun/ui`：AppShell（仅预览宿主）、PageHeader、Panel、Toolbar、DataTable、SearchInput、Select、Input、Button、ScoreBadge、Dialog、Alert、ErrorState、EmptyState、Icon。公共包版本 0.1.0，UI0 commit `5ce45fd4a4621cd8e5b04c4611c957aa379fec44`，兼容冻结起点 `4527ba4510dcb3ea8a3d1bf932dc46367070d1d5`。

当前 phase2 路由不再使用 `ui-port/previewUI`。旧插槽及其原生控件仅保留在历史候选，未作为本轮接入证据。没有复制公共源码、改公共组件或根 package/lock；主页仅编写布局、字段组合与原生 textarea（公共包没有 Textarea 导出）。Input/Select 直接提供 label，无嵌套 label。

DataTable 使用 columns/rows/稳定 rowKey；四个表头提供双向排序并同步 aria-sort，工具栏也可选择方向。rating 的 S→D / D→S、时间新旧、名称正反、百分比高低均限当前页；null 值两个方向都置末，不推算未知评分/进度。页面 CSS 仅控制自身布局/表格密度，保留公共 tokens，表格 13px。公共 AppShell 只包一次；真正主页接入时只挂 `Phase2Homepage` 内容，沿用全站 shell。

`shared-dialog.tsx` 是条件卸载弹窗的薄组合层：把页面初始焦点交给公共 initialFocusRef，卸载后在触发按钮重新启用时恢复焦点；showModal、Esc、Tab trap、pending 关闭限制均使用公共 Dialog。移除默认取消焦点、未保存草稿保护、提交防重和结果核对均有浏览器回归。

本 Worktree 的根 workspace 尚未传播公共包，按 UI.md 的包内隔离验证约定，`prepare-shared-ui.mjs` 只读公共 owner 已提交、clean 的源码，逐文件核对 Git blob，再用现有 TypeScript 5.9.3 编译到 **主页目录内被忽略的 node_modules/@ikun/ui**。没有绝对路径业务 import、跨 Worktree 链接、源码 vendor、根依赖/lock 修改。`shared-ui-pin.json` 固定版本；生成回执记录输入数与全部产物 SHA256。公共 owner 目录无写入。

这证明当前 Next 本地组合能运行，不等同 clean checkout 的 workspace frozen install。B0 仍需总管登记 website 对 `@ikun/ui` 的 workspace 依赖、root lock/build 顺序、全站唯一 CSS 引入，并以正式包安装替换隔离 QA 产物；页面 import 无需改写。phase2 共享 DTO import 同样等待总管传播。

## 运行和验证

在 **homepage-ui Worktree 根目录**，使用 Node 24.22.0 与既有独立 frozen 安装：

```sh
export PATH="/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH"
# 默认读取相邻 website Worktree 的已提交公共包；也可显式传已准备的 package 目录。
node apps/website/components/homepage-ui/prepare-shared-ui.mjs ../website/packages/ui
pnpm --filter @ikun/website typecheck
node --import tsx --test --test-reporter=tap apps/website/features/homepage/tests/view-model.test.mjs
pnpm --filter @ikun/website build
IKUN_HOMEPAGE_UI_PREVIEW=1 pnpm start:website
```

打开 `http://127.0.0.1:3700/prototypes/homepage`。预览仍需显式环境开关且拒绝 IKUN_ENV=production；不会替换正式 `/`。停止预览用 Ctrl+C。

浏览器 QA 使用本模块忽略的 `.tools`，不增加 workspace 依赖：

```sh
# 本模块尚未安装工具时执行；依赖版本固定，且不写 package/lock。
npm install --prefix apps/website/components/homepage-ui/.tools --no-save --package-lock=false --ignore-scripts --no-audit --no-fund @playwright/test@1.64.0
PROTOTYPE_CHROMIUM=/absolute/path/to/chromium node apps/website/components/homepage-ui/.tools/node_modules/@playwright/test/cli.js test --config apps/website/components/homepage-ui/phase2-playwright.config.cjs
node apps/website/features/homepage/verify-ui0.mjs
```

构建串行、cpus=1、heap=2048MB。未添加真实账号或密码字段，no-JS 密码项不适用于此页。

已通过：8 项纯视图测试、21 项浏览器交互、website typecheck / Next build；1440/1920/2560/390px 无整页横向溢出、13px 表格、390px 容器内部滚动。浏览器请求记录无外部/API 请求；63 个非本窗口基线文件未变化，未创建业务数据库。

最新证据为 `components/homepage-ui/evidence/reference/`；之前 `evidence/shared-ui/`、`evidence/phase2/` 与旧原型证据保持原样。最新验收结果在 verification.json / test-results.json / view-model-tests.tap，包含四个宽度截图、手机编辑、刷新失败保留。首轮回归发现旧测试精确标签定位不适配 required 标记，以及弹窗条件卸载晚于原生焦点回退；已分别补明确 aria-label 和卸载生命周期适配，没有绕过焦点断言。

## 用户参考图适配

按用户提供的深色宽屏参考图调整：标题右侧搜索/添加，6 个紧凑概览卡片，4 个近期时间卡片，评分/发现时间/名称优先的高密度表格。概览和 S/A/B 快捷筛选可点，行内增加查看资料；搜索支持 `/`、⌘K/Ctrl+K。演示设置默认折叠，保留持续可见的演示标记。

概览只统计当前页已加载的 active 项目，不是全库总量；参与中/已暂停直接按 progress_stage 计数。时间卡片仅来自 token_date/status，不新增事件模型，不补未知日期或制造倒计时。虚构 fixture 补充两个明确的预计日期，便于测试四卡布局。预计与确认始终区分；没有模拟 WSS/REST/数据库/Telegram 在线状态。

视觉仍使用唯一公共组件和冻结 tokens；未改侧栏/全站公共包，仅改本页布局与样式。1440px 可在本页表格内横向滚动，1920/2560px 操作按钮留在自己的单元格内，390px 概览三列/日期单行横向滚动。最新浏览器测试增加概览筛选、日期查看与双向排序回归。

## 给主页功能窗口的接入点

1. 挂载默认导出 `components/homepage-ui/phase2-homepage.tsx`，注入 `context/data/callbacks/query?`，沿用现有全站 shell；不要挂 demo preview。
2. AuthSession 映射真实 role/capabilities；Projects adapter 提供 DTO、cursor、revision 和公开 OperationResult。服务端仍执行权限、Idempotency-Key、If-Match 与 CSRF 校验。
3. 写回调只回传结果，UI 不改输入数据；接入方确认 succeeded 后重读/更新 props。unknown 先走 onReconcile，不重发写入；home remove/delete 保留监控关系。
4. 本页没有数据库、真实 API/SSE、轮询、持久任务或默认 demo fallback。演示仅存在 demo-fixtures/phase2-preview；发布候选不得默认启用预览写按钮。

尚未验证：根 workspace clean checkout/frozen install、可信 AuthSession 与真实 Projects adapter、跨浏览器/屏幕阅读器完整矩阵、生产部署。当前交付是可接入的主页 UI 原型，不代表业务链路或发布 READY。

## 紧凑布局调整

按用户反馈，近期时间卡片始终单行横向排列，显示当前页所有已填写日期的项目；超出容器时仅在时间区滚动，不再截断到前四条。S/A/B 等概览卡片桌面高度 56px、手机 48px，数值与标签同行；评分筛选按钮高度 23px。仍复用公共组件，没有新增业务字段、API 或数据库。

本次仅做小幅布局调整，未新增测试或重跑此前 21 项完整套件。已通过包含 TypeScript 检查的 Next 构建，并在实际预览中验证 1440/1920/2560/390px：日期卡片均同一行、整页无横向溢出、390px 时间区域可横向滚动；S 级筛选返回 2 行、恢复 10 行、编辑弹窗可打开和取消。实测与源码 hash 位于 components/homepage-ui/evidence/compact/validation.json。原 reference/ 的测试与截图保持为此前版本证据。
