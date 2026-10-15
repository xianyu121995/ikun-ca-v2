# 猎手监控 UI0 · 第二阶段交付

规范 `phase2-v1.0.0`，固定提交 `9699375c920465b5d802e7acff17b5421203e544`，tag `phase2-spec-v1.0.0`。本窗口基线 `3e0587dddc6304be0214ab41251a615d1aab20b9` 保留，新工作另提交到 `codex/hunter-ui`，未合并其他分支。

## 完成范围

- `model.ts`：页面私有传输形状、显式白名单投影、ID/未知值展示、权限能力门控、字段校验、北京时间日期转换。没有跨 Worktree import，也没有修改共享 DTO。
- `DiscoveryView.tsx`：只消费 props 的业务视图；回调由调用方注入。高密度表格、过滤排序、原始简介、资料面板、S/A/B/C/D/null、进度/日期/备注、确认弹窗、管理员账号注入展示和 readonly/loading/empty/error/refreshing/pending/unknown。
- `Prototype.tsx` / `fixtures.ts`：持续标明合成数据的内存演示。控制台可注入 superadmin/user、权限拒绝、超时、409、持续 pending、unknown、受理成功及空/加载/失败状态。无会话展示为 live 安全壳，数据为空且能力关闭，绝不回落 fixtures。
- `app/prototypes/hunter/page.tsx`：独立 Next 原型路由候选；没有修改正式 `/hunter`、root layout/globals 或 API。
- `preview.mjs`：仅静态 React 预览；使用基础已冻结的 React 与 tsx 依赖中的 esbuild，输出到忽略的 `.ui0-preview/`。不启动网站业务、worker 或 DB。
- `verify-ui0.cjs` / `model.test.ts` / `prototypes/hunter-discovery/qa/ui0/`：浏览器及模型证据。

## 数据与回调

| 输入/回调 | 映射与边界 |
| --- | --- |
| `items: DiscoveryDTO[]` | 逐字段对应 HunterDiscoveryV2；行键仅 discovery_id，canonical project_id 可 null，不能互换或自行生成 |
| `accounts: HunterAccountDTO[]` | 只有 superadmin 且 can_manage_hunter=true 才投影和显示；user DOM 不包含账号身份。只显示账号 DTO，不推断粉丝数、WSS/REST 或贡献归因 |
| `context` | mode、role、capabilities；缺省视为 live/只读，能力默认 false；客户端限制不替代服务端授权 |
| `onSaveResearch` | discovery_id、可空 project_id、expected_revision、完整 ProjectFields；仅为页面端口，冻结 API 尚未规定独立 Hunter 资料 PATCH，领域 owner 决定真实保存归属和未注册候选能力，不能由 UI 创造路由 |
| `onRequestMonitoring` | discovery_id、expected_revision、confirmed=true、完整 ProjectFields；不携带伪造 actor，不生成 canonical/command/subscription ID |
| `onCheckCommand` | 只接收已返回的同一 command_id；unknown 时用于核对，不重新发起确认 |
| `onRefresh` | 显式读取回调；refreshing 由调用方传入，保留已有数据；不内建轮询/付费/写入重试 |
| `onNextPage` | 原样传 opaque cursor。当前筛选/排序为本页展示；有本地过滤时禁用旧 cursor，不能把它用在其他查询。全局服务端筛选/分页适配留给领域 owner |
| `onManageHunters` | 管理入口回调；账号列表仅注入展示，未复制账号 CRUD 或后台监控 |
| `renderFrame` | 接入唯一 AppShell 的组合插槽；不得再嵌套第二个 shell |

ProjectFields 完整保留 name/rating/description/website_url/notes/category/progress_stage/progress_percent/token_date/token_date_status。未知 rating 显示未评分；未知粉丝和时间显示未知，未知进度为空。发币日期是日历日期，不当 UTC 时间戳。安全链接拒绝非 http/https 以及包含 URL 账号密码的地址，React 只渲染文本。

公开项目投影不保留 raw payload、Hunter 归因账号或私有扩展字段。公开 DTO 的服务端脱敏仍由领域 owner 实现，UI 投影不宣称已修复后台泄漏。

`review_state=tracking` 只显示“已确认”；accepted/succeeded 显示受理/待核实，running 命令显示“确认处理中”，全部不冒充远端监控运行。超时/unknown 锁住该项目的盲目重复写入，保留 command_id（若有）供读取核对；没有 command_id 时不编造占位 ID。实际远端状态须由未来 Tracking 适配器提供。

提交时同步锁防止重复回调，pending 禁止取消/Esc 关闭确认弹窗。403/409 保留草稿；409 不强制覆盖；未保存修改离开前确认。首次浏览器检查发现 Shift+Tab 约束不稳定，已补上显式首尾按钮焦点约束，最终完整复验通过。

## 公共 UI 依赖

没有复制 `@ikun/ui` 源码或修改其包。当前域视图使用原生 HTML 与页面专用 CSS module，未导出第二套通用 Button/Dialog/Table。最终组合需由总管在获授权阶段登记唯一 `@ikun/ui` 包和根 CSS，再将页面原型原生控件绑定到公共组件；本轮没有偷改 root lock、网站依赖或共享实现。`renderFrame` 预留 AppShell 组合能力，当前独立预览通过 renderFrame 注入本页参考图外壳，不同时注入第二个 AppShell。

## 验证与限制

- 网站 TypeScript 检查通过。
- 11 项纯模型检查通过：只读默认、伪能力不提权、管理员投影、私有字段白名单、ID 分离、未知值、D 评分、时间和安全 URL。
- 最新参考图评审版 21 项浏览器交互检查通过（另见 REFERENCE-REVIEW.md）：403/超时/409/pending/unknown/成功、权限、回调次数、防重、焦点、取消、空/加载/失败/刷新保留旧数据、cursor、1440/1920/2560/390px 无整页横向溢出。
- 浏览器运行时异常 0、外部请求 0、业务 API 调用 0。截图及结果位于 `../../prototypes/hunter-discovery/qa/ui0/`。
- 规范提交及读取的十个权威文件 SHA256 已与冻结内容逐字节核对，记录 `qa/ui0/spec-check.json`。

浏览器检查的是同一 React 入口的独立静态 bundle。Next 原型路由已 typecheck，但未执行整站 Next build/运行验收；避免与其他窗口并发构建，也不将独立预览当作根网站接线证明。真实认证、业务 DTO/API、canonical 映射、监控、跨服务命令、生产发布和 `@ikun/ui` 最终绑定均未验收。

## 复现命令

显式 cwd：`/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/hunter-ui`。

```sh
PATH=/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH pnpm --filter @ikun/website typecheck
PATH=/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH node --import tsx --test apps/website/features/hunter-discovery/model.test.ts
PATH=/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH node apps/website/features/hunter-discovery/preview.mjs
```

预览 <http://127.0.0.1:3800/prototypes/hunter>，只监听 loopback；停止按 Ctrl+C。另一个终端执行：

```sh
BROWSER_CHANNEL=chrome \
NODE_PATH=/Users/lvlei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules \
/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node apps/website/features/hunter-discovery/verify-ui0.cjs
```

修改只在本窗口三个白名单目录。未改其他窗口、共享组件/契约、root 配置、API、worker、schema、旧服务、Watch 或真实生产/平台数据；未执行 merge/cherry-pick/rebase/reset/amend/push/deploy。
