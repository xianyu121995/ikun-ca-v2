# 猎手监控 UI 最终版 V3 · 本地验收

状态：独立 UI 原型完成，等待用户验收；未集成、未部署、未交给程序窗口接入。

- Worktree：`/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/hunter-ui`
- 分支：`codex/hunter-ui`
- 本地预览：http://127.0.0.1:3803/prototypes/hunter-v3
- 原始 HTML 对照：http://127.0.0.1:3803/reference
- 只监听回环地址，不启动 Next 网站、监控 Worker、真实 API 或数据库。

## 视觉与公共组件

`reference/v3.html` 为用户提供的 V3 原件，SHA-256 为 `79dce14c995865fcebd2b26a28bd7d0c7892cc7314f9434ecbc86ba53464b168`。布局、密度、色值、面板和管理弹窗均据此实现。1440×960 实测：侧栏宽 190、顶部高 232、筛选栏高 63、表格宽 1250、页脚高 43，与原件一致；表格总高仅相差 0.5px。差值详见 `qa/v3/geometry.json`。

真实复用 `packages/ui` 的 `AppShell`、`Button`、`Input`、`Select`、`SearchInput`、`Badge`、`ScoreBadge`、`DataTable`、`Dialog`、`EmptyState`、`ErrorState`、`ToastViewport`，包括表格内置骨架屏、排序、弹窗焦点约束、通知关闭和搜索清除交互。图标由公共组件提供。

当前分支没有登记公共 UI 包。为避免修改根依赖、锁文件或其他模块，`setup.mjs` 从本仓库 Git 对象中的固定提交 `5ce45fd4a4621cd8e5b04c4611c957aa379fec44` 读取 `packages/ui`，在本目录 `.dependencies/ui` 内编译，并作为本原型的本地 `@ikun/ui` 依赖安装。来源树为 `8d7b1071db35a613bb9eb1868a52edd7ae958777`；不导入其他 Worktree 的源码，也没有跨 Worktree 依赖符号链接。生成依赖和构建产物均忽略，不提交公共组件副本。

V3 几何与配色覆盖只在 `.hunter-v3` 范围内生效；没有修改公共组件源码、全站 UI 规范或生产页面。保留公共控件的“未评分”文本、SVG 图标和必填标识。相对原 HTML 增强了未保存确认、输入校验、保存失败保留草稿和键盘焦点。

## 完成交互

- 页面标题“项目发现”，左导航“猎手监控”；初始表格全宽。
- 18 条明确标记的虚构项目；搜索涵盖名称、用户名、简介、研究结论和备注；时间、S/A/B/待评分、研究状态筛选可组合。
- 发现时间、名称、匿名猎手数量、评分双向排序；10 条分页及边界禁用。
- 只有“研究 / 编辑”打开右侧资料；行点击和 X 主页按钮不打开；关闭恢复全宽。X 按钮显示演示反馈，不导航到虚构账号。
- 编辑项目名称、X 简介、官网、研究结论、代币计划、评分、备注和关注标记；X 用户名只读；无“发现依据”或“发现信息”模块。
- 保存校验、400ms 模拟等待、重复提交保护、成功通知、失败后保留草稿并重试。
- 收起、切换项目、Escape 保护未保存草稿；加入监控确认时原子保存当前资料，仅更新本页演示状态，重复加入禁用。
- 猎手管理仅显示三项统计和用户名操作入口，无名单、账号枚举或自动补全；添加默认停用，用户名不区分大小写去重，启用/停用/移除反馈，停用和移除二次确认。
- 页面状态测试入口包含正常、加载、失败重试、空数据、下次保存失败开关；分页在加载/失败/空数据状态禁用。
- 原生弹窗焦点约束、Escape 和焦点返回；手机窄栏、表格横向滚动和覆盖式资料面板。

## 运行

从本 Worktree 根目录，使用 Node 24.22.0 和 pnpm 10.33.1。现有根依赖已安装；首次准备原型本地依赖：

```sh
node apps/website/features/hunter-discovery/v3/setup.mjs
node apps/website/features/hunter-discovery/v3/preview.mjs
```

安装使用本 Worktree 的离线 `.pnpm-store`，不修改根清单或根锁文件。可用 `IKUN_UI_SOURCE` 指向包含固定提交的 Git 仓库；默认读取当前 Worktree 的 Git 对象。端口可由 `HUNTER_V3_PORT` 指定；Ctrl-C 只停止此静态预览。修改源文件后重启预览脚本重新打包。

## 测试与证据

2026-10-15 本地验收：

- 网站全量 TypeScript 检查通过，包括 V3 公共组件类型。
- 7/7 逻辑测试通过：夹具、搜索、组合筛选、时间边界、排序、URL 校验和用户名规则。
- 30/30 Chrome 浏览器验收组通过：全部筛选、排序、分页、编辑、保存、失败重试、草稿确认、加入确认、猎手增启停删、弹窗键盘和刷新复位。
- 390、980、1100、1350、1440、1920、2560px 七档宽度截图与断言通过；手机导航保持竖排，关闭面板恢复宽度，页面无全局横向溢出。
- 最终浏览器运行错误为 0；请求只有本地文档、JS、CSS 和参考 HTML，均为 GET，没有 fetch/XHR/WebSocket/外部请求。服务器另有 CSP `connect-src 'none'`。
- 根清单、锁文件、应用路由、公共包、其他模块均无改动。

```sh
node node_modules/typescript/bin/tsc -p apps/website/tsconfig.json --incremental false
node --import tsx --test apps/website/features/hunter-discovery/v3/model.test.ts
# 预览运行时，在可提供 playwright/test 的 Node 环境：
BROWSER_CHANNEL=chrome node apps/website/features/hunter-discovery/v3/verify.cjs
```

本机浏览器测试运行环境可用：
`NODE_PATH=/Users/lvlei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules`。

结果及截图位于 `apps/website/prototypes/hunter-discovery/qa/v3/`：

- `browser-results.json`：逐项测试与请求记录。
- `geometry.json`：原 HTML 与实现的主要区域尺寸。
- `logic-results.txt`、`typecheck-results.txt`、`boundary-audit.json`：逻辑、类型和范围证据。
- `discovery-{390,980,1100,1350,1440,1920,2560}.png`：默认表格。
- `editor-{390,980,1100,1350,1440,1920,2560}.png`：右侧资料。
- `hunter-management-1440.png`：无猎手名单的管理弹窗。
- `reference-1440.png`：原件对照。

## 新增文件清单

全部改动仅新增在两个原型目录，没有替换旧原型：

| 文件（相对 Worktree） | 用途 |
| --- | --- |
| `apps/website/features/hunter-discovery/v3/App.tsx` | V3 页面与内存交互 |
| `apps/website/features/hunter-discovery/v3/v3.css` | V3 局部布局样式 |
| `apps/website/features/hunter-discovery/v3/model.ts` | 演示投影、筛选排序及校验 |
| `apps/website/features/hunter-discovery/v3/model.test.ts` | 7 项逻辑测试 |
| `apps/website/features/hunter-discovery/v3/entry.tsx` | 独立浏览器入口 |
| `apps/website/features/hunter-discovery/v3/preview.mjs` | 回环静态服务器与打包 |
| `apps/website/features/hunter-discovery/v3/setup.mjs` | 固定公共 UI 版本的隔离准备 |
| `apps/website/features/hunter-discovery/v3/package.json` | 原型私有依赖 |
| `apps/website/features/hunter-discovery/v3/tsconfig.json` | 独立类型检查 |
| `apps/website/features/hunter-discovery/v3/.gitignore` | 忽略生成物 |
| `apps/website/features/hunter-discovery/v3/verify.cjs` | 30 组浏览器验收 |
| `apps/website/features/hunter-discovery/v3/reference/v3.html` | 用户提供的原件 |
| `apps/website/features/hunter-discovery/v3/reference/reference.css` | 原件样式提取 |
| `apps/website/features/hunter-discovery/v3/reference/seed.json` | 原件虚构数据 |
| `apps/website/features/hunter-discovery/v3/reference/provenance.json` | 原件 SHA 与公共 UI 固定版本 |
| `apps/website/features/hunter-discovery/v3/README.md` | 本验收说明和完整文件清单 |
| `apps/website/prototypes/hunter-discovery/qa/v3/**` | 上述测试结果与截图 |

所有修改仅当前页面内有效，刷新即恢复。未验证真实 API、数据库、监控任务或线上接入；本轮范围不包含这些内容。等待用户验收后，再由猎手监控程序开发窗口接入。
