# Tracking UI0 交接 · 2026-10-15

此文为历史状态管理/事件表候选的交接记录。当前路由已按用户正式 HTML 定稿替换，现行交接以 [FINAL-HANDOFF.md](./FINAL-HANDOFF.md) 为准。

状态：第二阶段独立 UI 候选，已隔离消费冻结公共组件；正式 workspace 组合验收、真实接入与发布均未进行。

本轮视觉调整：以用户提供的事件中心截图为信息结构模板，推文列表成为默认主视图；管理表与演示设置默认收起。保留公共冷灰/青绿终端 tokens 与唯一 AppShell。已保留前一候选提交 `a0694ba971a63e19fa90706e143e0cfbd8abd4f3`，本轮另提交。

## 冻结依据

- 规范版本：`phase2-v1.0.0`，提交 `9699375c920465b5d802e7acff17b5421203e544`。
- 注解 tag：`phase2-spec-v1.0.0`；tag 对象与 commit 不同，使用 `git rev-parse 'phase2-spec-v1.0.0^{commit}'` 核对。
- 只读过 README/API/DTO/STORAGE/UI/OWNERSHIP/RELEASES、ownership.json/releases.json/source-freeze.json 与对应展示类型。
- 原分支 `codex/tracking-ui`，保留祖先 `d2e1093a86c2366dd4047973fad55f9271227eaa`。没有 merge/cherry-pick/rebase/reset/amend/push/deploy。
- 保留 UI0 提交 `fe870e4242695f175d0730cffd8795e109df6ac2`；本轮另提交公共组件消费及演示交互完善。
- 公共组件来源固定为 `4527ba4510dcb3ea8a3d1bf932dc46367070d1d5`，只从 Git 对象打包，不使用公共组件窗口未提交内容。

## 路径与行为

- `apps/website/app/tracking/page.tsx`：原页面入口改为本页原生 React 候选。默认 `/tracking` 是空的只读展示容器，无身份、样例项目或模拟写按钮；只有显式 `/tracking?mode=demo` 才加载演示控制台。
- `features/tracking/tracking-view.tsx`：纯 props/callback 页面，默认能力关闭；不调用 API，不读取认证或数据库，不持久化业务状态。
- `features/tracking/types.ts`：本页专用结构类型，逐字段对应冻结 DTO。没有跨 Worktree import、类型源码链接或 shared contracts 修改。
- `features/tracking/view-model.ts`：纯字段转换、显示、筛选、ID 校验、回执身份校验、安全原文 URL 和动作可用性。
- `features/tracking/tracking-feed.tsx`：本页专用推文事件列表，以原生 details/summary 实现行内展开；不修改公共 DataTable 的冻结接口。只接纳传入订阅与项目双标识匹配的动态，支持项目/正文搜索/北京时间日期与新旧排序，以及暂停期间的匹配动态计数。
- `features/tracking/demo-*`：固定虚构 ID 与显式 demo 回调；无真实角色、存储、请求、任务队列或 ID 生成器。计时等待只用于观察 pending。
- `features/tracking/tracking-workspace.tsx`：唯一公共 AppShell 包裹本页；显式账号路径 `/auth`，模拟身份持续标记；公共样式只在本页边界导入，不改根布局。
- `features/tracking/scripts/prepare-ui.mjs` 与 feature 内 `package.json`：冻结公共包的隔离构建与消费候选；生成 tar/node_modules 均忽略。root manifest/lock 和其他窗口文件未改。
- 原 `public/tracking-prototype/` 静态候选保留，其旧浏览器测试只调整 `/tracking` 入口的预期。它仍可单独评审，不作为发布入口或真实业务。

## DTO 与视图对应

| 冻结字段 | 本页展示和约束 |
| --- | --- |
| subscription_id / project_id | 始终分别保留，详情完整显示；操作回调传 subscription_id、project_id、revision；不按 handle 生成身份 |
| desired_state | 单独目标列：期望运行/停止/移除 |
| observed_state | 单独远端观测列：运行/停止/未知/不存在；不从 connected 或 ACK 推导 |
| operation_state | 单独回执列：已受理/排队中/执行中/已确认/失败/结果待核实 |
| connection | 单独来源连接列：未配置/连接中/已连接/已断开；不是监控成功 |
| last_tweet_at / timestamps | UTC ISO 输入，北京时间显示；null 显示未知，不补当前时间 |
| revision | 从输入投影原样传回，409 展示错误并保留数据/筛选，不自动覆盖或重提 |
| TrackingActivityV2 | 独立 activity/subscription/project/tweet ID；正文纯文本。occurred_at=null 时按 received_at 展示并注明发生时间未知 |
| CommandResultV2 | 受理与完成分开；拒绝错绑项目/订阅的回执。空引用仅保留未知，不生成占位业务 ID |
| Public error | 显示 code/message/retryable/request_id；原生 Error.message/stack 不直接输出 |

`types.ts` 不充当新的公共传输权威；待 B0 传播共享类型后由 owner 做只读 import 替换。目前不跨 Worktree 链接。

## 权限、确认与回执

- 只有 `role=superadmin` 且 `capabilities.can_manage_tracking=true` 才显示业务写入口。默认缺能力为 false；user 保留列表、详情与只读回执查询。此判断不代替服务端认证与授权。
- 每个按钮均有注入回调或 disabled 原因，未绑定能力不模拟成功。同步 in-flight guard 防重复点击，pending 时禁用按钮与模态关闭。
- accepted/pending/running 禁止重复副作用；unknown 或写入超时展示“结果待核实”，只提供原回执查询，不提供盲目重试。查询本身不会将 UI 乐观改成成功；需调用方推送新的权威投影/revision。
- 加入需要已注册项目和明确 confirmed；不会创建 canonical ID。加入超时/未完成同样封锁重复加入，使用独立只读查询回调。
- 移除确认只针对监控订阅，不改主页。回调没有 home_membership 或联动删除参数；历史推文保留。
- 刷新期间保留原表格，刷新失败展示公开错误并保留搜索/排序。初始加载、空、错误分别可评审；live 没有 fixture fallback。

## 注入接口

`TrackingView(TrackingProps)` 接收 subscriptions、activities、mode、role/capabilities、loading/refreshing/error、已注册 projects。

回调为 `onRefresh / onAction / onAdd / onReconcile / onReconcileAdd`。后两者只查询原结果。onAction/onAdd 返回 CommandResult 投影，不等于页面自己执行任务。查询后更新 props 才能显示已核实的新状态。

本页通过 feature 内依赖实际 import `@ikun/ui` 的 AppShell、Button、Select、SearchInput、Badge、Panel、PageHeader、Toolbar、DataTable、Dialog、Alert、EmptyState、ErrorState。没有复制公共源码或另造公共导出；页面仅保留状态映射、布局和弹窗关闭后的触发点/搜索框焦点恢复。Dialog 负责原生 modal、Tab trap、pending 与取消初始焦点。AppShell 只有一个，三个业务入口，账号显式 `/auth`。主布局、globals、root page、proxy 和通用 API 未动。

包内脚本使用同 Worktree 的 Node24/TypeScript 构建固定 Git 来源，在临时目录打包后安装进 feature；不自动安装 peers，使用网站已有 React。正式 `workspace:*` 依赖、root lock 与构建顺序需要 B0 登记。当前证据不代表 clean checkout/frozen install 或正式全站组合验收通过。

本页客户端筛选/排序仅作用于当前注入页，显示上限100条。PageV2 的 cursor、下一页、全局服务端搜索由领域适配器持有，可经 toolbarSlot 注入控件；不把客户端排序当作服务端分页或 checkpoint。

## 尚缺的 live 适配（本轮不实现）

真实 AuthSession/capabilities；同源 BFF；Idempotency-Key、If-Match/ETag；PageV2 cursor；真实 CommandResult 与 subscriptions 的权威刷新；稳定 X user_id 解析；SSE 去重/重放；真实错误脱敏；正式 workspace 的公共包登记与组合构建。页面不直接实现这些能力。

## 验证

命令见 README.md，结果存 evidence/validation.json 和 evidence/browser-results.json，绑定规范 SHA。浏览器矩阵 1440/1920/2560/390：整页无横向溢出，横向滚动只在本页表格容器，手机弹窗不越界。

验收涵盖默认只读、四状态差异、权限、加载/空/错误、刷新保留旧数据、回调拒绝/409/超时/pending/unknown/成功、取消默认焦点/Tab循环/焦点恢复、pending不能Esc关闭、防重复提交、加入待核实锁、订阅移除不改主页、未知发生时间、纯文本/安全链接、无业务请求和无伪造 session。

新增验收覆盖公共组件真实 DOM、唯一 AppShell、启动→停止→恢复、两条预置推文/最近时间/暂停缓冲。演示默认7条有效订阅，另有1条已移除；可加入的 Nimbus 与可启动的 Beacon 各有独立固定 ID。

模板调整验收：默认8条虚构推文、管理与测试设置折叠、推文占据主阅读区、键盘展开且一次一条、筛选组合与北京时间跨日、未知发生时间仍标明接收时间、手机首屏能看到推文。未注入评级或译文 DTO；模板中的评级筛选未伪造，中文译文/摘要区明确未接入。原文与摘要纯文本渲染；demo 不提供虚构原文链接。

未包含密码表单，no-JS 密码检查不适用。未执行真实API/认证/worker/平台/DB/生产构建/部署；仅新增 feature 内冻结公共包消费，不改 root lock。测试通过只证明本 UI 候选，不证明真实监控或后端验收。
