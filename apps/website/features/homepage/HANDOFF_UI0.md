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

## 公共组件与依赖门禁

已只读核对公共 UI 冻结导出/props，基线 `4527ba4510dcb3ea8a3d1bf932dc46367070d1d5`。未复制 `@ikun/ui` 源码、未改 packages/ui、root lock 或构建顺序。

保留本页 `ui-port.tsx` 的显式组件 Provider；预览仍注入此前本页的原生 previewUI。新行为仅补 optional Dialog pending、默认 button 类型和焦点边界。此原生预览不是正式公共 UI 接入证据。

待全站 UI owner/B0 获授权传播后绑定唯一 `@ikun/ui`：Button 的 pending/type、Input/Select 的 label wrapper、ScoreBadge(D/null)、DataTable columns/rowKey/状态、受控 Dialog open/onOpenChange/pending、Alert/ErrorState/Toast，以及 AppShell。Input/Select 当前 native 插槽与正式 label props 需 adapter 审阅；不要直接把正式组件塞进嵌套 label。页面不创建侧栏/第二个 AppShell；216px 壳层由全站入口提供。tokens/系统字体/13px 表格已按 UI.md 应用。

## 本轮验收与命令

在 **homepage-ui Worktree 根目录** 使用 Node 24.22.0；依赖保持本 Worktree 独立冻结安装。

```sh
export PATH="/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH"
pnpm --filter @ikun/website typecheck
node --import tsx --test apps/website/features/homepage/tests/view-model.test.mjs
pnpm --filter @ikun/website build
IKUN_HOMEPAGE_UI_PREVIEW=1 pnpm start:website
PROTOTYPE_CHROMIUM=/absolute/path/to/chromium node apps/website/components/homepage-ui/.tools/node_modules/@playwright/test/cli.js test --config apps/website/components/homepage-ui/phase2-playwright.config.cjs
```

预览：`http://127.0.0.1:3700/prototypes/homepage`。QA 工具沿用本模块忽略的独立 .tools，不改 workspace 依赖；8GB 构建串行，cpus=1。未使用任何真实账号/口令，因此密码表单 no-JS 项不适用于此页面。

证据在 `components/homepage-ui/evidence/phase2/`：8 项纯视图测试 TAP、16 项浏览器结果、1440/1920/2560/390px 截图、刷新失败保留、手机编辑与 owner/冻结核对。浏览器覆盖 callback payload、成功/权限拒绝/409/超时/accepted/pending/unknown、重复提交、默认只读、live 不回退、Tab 双向焦点与取消/关闭后恢复。

尚缺：正式 @ikun/ui 绑定与其组合验收、phase2 共享类型依赖传播、可信 AuthSession、Projects live adapter、真实业务链路和部署。由总管审阅新 commit，再按批次放行；不合并或继续后端阶段。
