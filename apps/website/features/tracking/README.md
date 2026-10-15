# 猎手项目追踪 · HTML 正式定稿

当前入口由 `final/tracking-page.tsx` 实现，定稿依据为用户提供的 `ikun-hunter-project-tracking-ui-prototype (2).html`。原件 SHA-256：`80a136cfbc5597a91a9a1f281c741de4503b44df7f8e20255decf869b30ed82a`。

五张统计卡、备注优先的纵向推文列表、S/A/B/时间/重要推文筛选与每页6条分页，严格按附件组织。只有点击“监控账号总数”才打开账号管理窗口，可搜索、添加、删除并二次确认删除。没有右侧常驻项目栏、快捷筛选栏、事件展开行、AI摘要区或演示测试控制台。

在本 Worktree 根目录：

```sh
export PATH='/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:'"$PATH"
node apps/website/features/tracking/scripts/prepare-ui.mjs
pnpm dev:website
```

- 默认：<http://127.0.0.1:3900/tracking>
- UI0 演示：<http://127.0.0.1:3900/tracking?mode=demo>

首次预览前，`prepare-ui.mjs` 使用本 Worktree 已安装的冻结依赖准备公共组件。脚本只从 Git 提交 `4527ba4510dcb3ea8a3d1bf932dc46367070d1d5` 打包未修改的 `@ikun/ui`，安装到本 feature 的忽略目录。它不修改 root / website manifest 或 lock，不读取其他窗口未提交代码。需要本 Worktree 已完成基础 `pnpm install --frozen-lockfile` 与 `pnpm build:shared`，并且本地 Git 对象包含上述提交。不要同时启动另一个网站进程占用3900；不需要启动 worker 或数据源。

这是包内隔离消费候选；正式 workspace 依赖登记与 clean checkout/frozen install 验收仍由总管完成。

```sh
pnpm --filter @ikun/website typecheck
node --import tsx --test apps/website/features/tracking/final/model.test.ts
```

浏览器验收使用环境里独立的 Playwright；无需改 root 依赖：

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
node apps/website/features/tracking/browser.test.mjs
```

演示初始10个账号、12条虚构推文及虚构互动数据，样例媒体按原型以本地展示卡渲染。增加账号不会伪造历史推文；删除账号只从本页名单及信息流隐藏记录，原始演示推文数组保留。页面“刷新”重置筛选；浏览器刷新恢复初始样例。原文按钮按原型给出“演示无真实链接”的明确反馈。

公共组件复用 AppShell、PageHeader、Panel、Button、Input、Select、SearchInput、ScoreBadge、Badge、DataTable、Dialog、Alert、Skeleton、EmptyState、ToastViewport、Icon。页面 CSS 仅负责附件布局与媒体展示；账号管理的公共 Dialog 通过本页作用域适配为右侧窗口，保留原生 modal、键盘焦点约束和取消默认焦点。

默认 `/tracking` 仍为空的只读展示；`?mode=demo` 才启用样例和内存增删。`final/model.ts` 是本页展示模型，不是新的公共 DTO；只使用明确的本地 `demo-*` 渲染键，不创建 canonical ID。评分、备注与媒体的真实数据适配仍由接入方完成。本页没有请求、认证、持久化、引擎、队列或数据库实现。

当前交接见 [FINAL-HANDOFF.md](./FINAL-HANDOFF.md)。旧事件列表和状态管理实现保留于 Git 历史与本 feature 的历史文件，当前路由不再渲染；旧静态原型亦保留，不作为正式页面。历史 UI0 文档不代表当前页面或真实后端验收。
