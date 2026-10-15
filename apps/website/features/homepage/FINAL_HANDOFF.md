# ikun.ca v2 主页 UI 最终交接

接收窗口：「主页功能开发」。本次仅交付主页 UI、演示宿主与交互证据；真实数据接入由接收窗口实施。视觉及交互基准唯一指定为用户的 `ikun-home-ui-hourly-date-filter.html`，不重新设计。

## 交付入口

| 内容 | 仓库路径 |
|---|---|
| 最终可独立打开的 HTML | `apps/website/components/homepage-ui/prototype/ikun-home-ui-hourly-date-filter.html` |
| HTML 的输入/输出 SHA256 与修复清单 | `apps/website/components/homepage-ui/final-reference.json` |
| HTML 本地验收入口 | `/prototypes/homepage/html` |
| 公共组件接入版入口 | `/prototypes/homepage` |
| 公共组件页面、抽屉、页面专属样式 | `apps/website/components/homepage-ui/reference-homepage.tsx`、`reference-editor.tsx`、`reference-homepage.css` |
| 接入 props、草稿及回调定义 | `apps/website/features/homepage/reference-types.ts` |
| 日期、小时、排序、校验 | `apps/website/features/homepage/reference-model.ts` |
| 明确标记的演示数据及模拟宿主 | `reference-fixtures.ts`、`components/homepage-ui/phase2-preview.tsx` |
| 测试与截图 | `apps/website/components/homepage-ui/evidence/html-v2/` |

HTML 保留原稿的 CSS、布局、S/A/B、最近 3 个事件、9 条分页、搜索、发现日期、排序、增改、移除、批量移除、完成记录与恢复。仅修复实际发现的选择范围、恢复原进度、链接校验、焦点及分页问题。它是自包含的验收稿；不把其 DOM/CSS 当成另一套全站组件实施。

真正接入页面通过 `@ikun/ui` 复用 AppShell、Panel、Toolbar、DataTable、SearchInput、Input、Select、Button、ScoreBadge、Badge、Dialog、Alert、EmptyState、ErrorState、Icon。样式仅作用于 `.hpv2-*` 组合，不修改公共组件实现、根页面/布局/样式或其他模块。原冻结字段、只读模式、C/D/未评分等兼容处理仍保留；不把它们写回共享契约。验收控制台仅属于明确 opt-in 的原型宿主，不进入正式产品页面。

## 实际修复

1. 原 HTML 的“全选”按未排序数组截页，与屏幕上的排序不一致；现以排序后的当前页稳定 ID 为准。
2. 搜索、排序和翻页后遗留隐藏选择，可能进入批量移除；现切换条件或页码即清空选择，部分选择显示半选状态。
3. 原 HTML 在编辑为已完成时先覆盖为“研究中”，恢复丢失原进度；现保存移除前进度。公共组件版也与最终稿一致：选择已完成并保存即转入完成记录。
4. 原型官网输入接受危险 URL，演示域名会打开无效页面；现校验 http/https 且拒绝用户凭据，`.example` 只显示演示提示。
5. 关闭的抽屉可获得键盘焦点、弹层缺少 Esc/焦点约束；现背景及隐藏层 inert，Esc 安全取消，焦点在弹层内循环并返回触发器。所有新增属性不改变布局。
6. HTML 的演示 ID 改为页面内递增以避免同毫秒重复；页数超过 5 时显示当前页附近的页码。均为原有交互的修复。

## 真实数据接入约定

- 直接使用 `ReferenceHomepage`，注入 `context`、`data`、`callbacks`、`milestones`、`archiveNotes`、`asOfDate`。不要把 demo 宿主或 fixtures 导入正式数据提供者。live 未接入时显示 `AUTH_NOT_CONFIGURED`，不回退演示数据。
- 只有 `role=superadmin` 且 `capabilities.can_edit_projects=true` 才启用写操作；这只是展示控制，真实服务端必须再次鉴权。普通 user 可搜索、筛选、排序、分页及查看资料。
- 项目 ID、revision、发现/创建/更新时间均由真实数据提供者给出。新增草稿没有 ID/发现时间等写入字段；界面不为未知资料编造服务端值。
- 项目重要时间是**独立事件**，不能把“主网上线”“奖励快照”等时间覆盖 `token_date`。页面模型为 `{project_id,date:'YYYY-MM-DD'|null,hour:'00'..'23'|null,title,status}`；所有日期/小时按 **Asia/Shanghai** 墙上时间解释。00 与 23 均原样保存、回显、展示和排序；未知小时为 null，显示“小时未确认”，不能默认推断为 00。新增时选择日期的默认 00 时属于明确可编辑的草稿默认值。
- 发现日期按服务端 UTC 时间转换后的**北京时间自然日**筛选；例如 `2026-10-14T17:00:00Z` 属于 10 月 15 日。未知发现时间在选定某天时不匹配。`onDiscoveryDateChange(date|null)` 仅为主页 UI 回调，不是新公共 API 字段。
- 发现日期可与搜索、评分及既有进度条件组合；“全部日期”仅清空日期，“清除筛选”清空组合条件。评分计数按发现日期计算。上方近期事件保留最终 HTML 的范围：跟踪项目 + 评分 + 事件时间窗口，不跟随发现日期/搜索词；避免把“发现时间”误作“事件时间”。
- 最近事件最多 3 条，先按日期、再按小时、再按稳定 ID 排序。同日 00 时在 23 时之前，未知日期排后。事件时间状态不等于发生事实；原型均标明预计。
- 当前最多展示已加载的 100 个项目，页码只是当前加载范围的 9 条切页。全量搜索/日期筛选/排序需由真实数据适配器保障；`next_cursor` 是 opaque 值，只传给 `onNextPage`，不可用页码代替服务端游标。
- `onCreateDraft`/`onUpdateDraft` 接收字段白名单与独立 milestone。选择“已完成”后保存会明确携带 `archive_after_save=true`；适配器应以一次授权操作保留原进度、设置 completed 并移出主页。
- `onArchive([{project_id,revision},...])` 是一次已确认的单项/批量完成意图；成功后才变更列表及最近事件。`onRestore(target)` 恢复主页成员状态及已保存的原进度，保留评级、官网、备注、重要日期及小时等资料。演示中新建即完成的项目按其新建默认进度“研究中”恢复；真实服务应明确自己的新增/恢复规则，不伪造历史。
- 删除主页条目与完成移除保留冻结的独立意图；不会物理删除项目、清理 ID 引用或停止其他监控。领域适配器不能从这些按钮推导跨模块命令。
- failed/403/409 不应用成功结果；accepted/pending/running/unknown 不显示为成功。未核实前禁止重复写入；仅 `onReconcile` 确认成功后解除锁定。由接收方实现幂等键、revision/If-Match、持久化和审计，原型未实现这些服务端能力。

**接线前仍需领域/总管协调**：小时事件、完成记录原进度和发现日期全量查询尚不在当前冻结 Projects DTO/API 中。本交付只提供主页自有类型及回调，不修改 contracts、API、schema、迁移或 projects.db。真实落库方式及 API 映射由接收方与领域 owner 审阅后落实。

## 公共组件及运行

全站公共 UI 依赖固定为 `5ce45fd4a4621cd8e5b04c4611c957aa379fec44`，冻结规范固定为 `9699375c920465b5d802e7acff17b5421203e544`。本窗口通过只读构建公共包，在本 UI 目录的 ignored node_modules 中验证裸包导入；没有复制公共实现或链接其他窗口依赖。根 workspace 注册与干净 checkout 的依赖传播仍归总管 B0，不能把本窗口已安装环境等同全站安装验收。

在 homepage-ui Worktree 根目录，Node 24、既有 frozen 安装环境下：

```sh
node apps/website/components/homepage-ui/prepare-shared-ui.mjs ../website/packages/ui
pnpm --filter @ikun/website typecheck
pnpm --filter @ikun/website build
IKUN_HOMEPAGE_UI_PREVIEW=1 pnpm --filter @ikun/website start --hostname 127.0.0.1 --port 3700
```

打开 `http://127.0.0.1:3700/prototypes/homepage/html` 体验最终 HTML，或 `/prototypes/homepage` 体验公共组件接入版。HTML 也可直接从交付文件打开。两者均明确标记演示；修改仅在当前页面内存，刷新恢复初始数据。两条预览路由均需 opt-in，`IKUN_ENV=production` 时返回 404。

测试命令（浏览器测试使用已安装的 Playwright 工具目录；没有修改根依赖）：

```sh
node --import tsx --test apps/website/features/homepage/tests/view-model.test.mjs apps/website/features/homepage/tests/reference-model.test.mjs
node apps/website/components/homepage-ui/.tools/node_modules/@playwright/test/cli.js test --config apps/website/components/homepage-ui/html-v2-playwright.config.cjs
node apps/website/features/homepage/verify-final-ui.mjs
```

本机 Chromium headless shell 需按安装位置通过 `PROTOTYPE_CHROMIUM` 指定；具体版本/路径在测试 JSON 的 config 中。`.tools` 与 node_modules 均不提交。

## 验证结论与边界

以 `evidence/html-v2/verification.json`、`test-results.json`、`model-tests.tap`、`typecheck.log`、`build.log` 为本轮证据；更早证据和 HANDOFF 为历史，不能替代本轮结果。

- 42 项浏览器交互（HTML 8 项、公共组件版 34 项）与 16 项纯模型验证；1440/1920/2560/390 宽度验证属于公共组件版。HTML 维持原稿宽屏布局，不另外设计移动版。
- 覆盖搜索/日期/评分组合及清空、四种排序与列头排序、00/23 小时保存回显和同日排序、分页/选择、增改、取消、单项/批量完成、完成记录恢复、只读、错误/冲突/超时与核对、防重复提交、焦点/键盘、空态/加载/刷新。
- 浏览器测试逐项检查无页面 JS 错误、无外部请求和 `/api/` 请求。源码检查无页面网络客户端，保护文件逐字节比对；实际数量见 verification。
- 当前状态是本地 UI 自动化验收通过、等待用户最终体验与真实数据接入；不等于服务端持久化、真实认证、全量查询、主站集成或生产验收。本次未部署、未修改其他窗口、未触碰 projects.db。

Git 分支 `codex/homepage-ui`；最终 SHA 以本交付提交和聊天报告为准，由总管按流程审阅合入，不在此窗口合并或部署。
