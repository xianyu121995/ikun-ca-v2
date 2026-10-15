# UI0 公共组件交接 · phase2-v1.0.0

状态：本轮包内代码与隔离 UI 验证完成，供总管审阅；不代表 B0、正式组合、真实认证或发布验收通过。原分支 codex/website，冻结基线 `4527ba4510dcb3ea8a3d1bf932dc46367070d1d5` 保留，新成果另提交。

## 采用规范和所有权

只读采用规范提交 `9699375c920465b5d802e7acff17b5421203e544` / tag phase2-spec-v1.0.0，已读取 README/API/DTO/STORAGE/UI/OWNERSHIP/RELEASES 与 ownership/releases/source-freeze JSON。规范 SHA256 与当前源码 hash 记录在 UI0-VALIDATION.json。

本轮只修改 packages/ui/**。未 merge/cherry-pick/rebase/reset/amend/push/deploy；根依赖锁、layout/globals/page/proxy、contracts/runtime、Auth/API/DB/worker 源码和数据均无改动。Node24.22.0、React19.3.1、TypeScript5.9.3 与既有依赖版本沿用，未新增依赖。新增包内脚本仅是测试工具，不增加正式服务。

## 公共接口增量

已有 20 个组件导出及其他既有导出均保留；tokens 未改。没有删除或新增必填 props，既有调用继续可编译。

| 接口 | 当前冻结行为 / 兼容增量 |
| --- | --- |
| AppShell | 三业务入口 /、/hunter、/tracking；账号默认从 /account 改 /auth，遵循新规范；显式 account.href 仍可覆盖 |
| LoginPanel | 字段名 username/password 与回调签名不变；固定 method=post、action=/api/v1/auth/login，无可覆盖 action 的参数；JS 绑定时阻止原生提交并回调 |
| Button | 新增可选 readOnly、disabledReason、operationState、mode、canExecute；未使用这些参数时保留原行为 |
| UiOperationState | 新增纯展示类型 idle/pending/running/succeeded/failed/unknown，不是新传输 DTO；不生成 ID、不操作队列 |
| Button pending/running | 禁用重复提交并 aria-busy；unknown 优先于旧 pending 标记，展示待核实原因且不触发重试 |
| Button readOnly | 禁用此操作并显示“当前账号只读”；不影响其他读取、搜索、取消动作 |
| Button mode=live | canExecute 必须显式 true，否则禁用并显示能力未确认；仅作为业务写按钮展示规则，服务端仍要验权 |
| Button disabledReason | 非 pending 的禁用状态显示原因并 aria-describedby 关联；有原因时增加包裹 span，原 DOM 在未提供新参数时保留 |
| Alert/ErrorState | 增加可选公开 code 展示；保留 requestId/说明/重试回调，不导入共享传输类型或显示 raw payload |
| Dialog | 新增可选 destructive；默认聚焦 data-dialog-cancel 标记，仍支持 initialFocusRef；无标记时关闭按钮是安全回退 |
| Dialog pending | 禁止 Esc/关闭按钮/背景关闭/子表单提交；焦点移入 dialog。method=dialog 与 submitter formmethod=dialog 不能绕过受控关闭 |
| DataTable/SearchInput/ScoreBadge | 保留接口；加载、刷新保留旧数据、空/错误、受控搜索、未评分语义不变 |

需总管协调的行为变化只有 `/auth` 默认入口及固定 POST 目标，均为本版 UI.md 的明确要求。没有提出非兼容 props 变更。使用新 disabledReason 的页面若依赖 Button 的直接父子 CSS 选择器，需按新包裹 span 适配；没有原因时原 DOM 不变。

## 页面 owner 使用约定

1. 各页面仍只读唯一 @ikun/ui 接口，不复制实现。领域 adapter 从真实 AuthSessionV2 提供能力与状态，live 缺能力默认 false。user 只能读业务；本包不读取角色凭据或实施认证。
2. unknown 传给 Button.operationState 并显示待核实，不用可点击重试或成功通知覆盖它。202/ACK/ready/SSE 不是 running/connected 的证据。
3. 公共 ErrorState 的 onRetry 只用于领域层明确允许的重试。403、409、未实现和结果未知不通过 UI 自行重发副作用。
4. 破坏性 Dialog 使用 destructive，取消按钮带 data-dialog-cancel；父层 pending 时也应禁用自己的操作与关闭回调。组件不会替父层判断业务权限。
5. LoginPanel 的固定 POST 不是 Auth 后端完成。B1 owner 须对表单编码安全拒绝/处理、CSRF/Host/Origin 等执行真实验证；UI0 只检查浏览器回退不会 GET 密码。

## 本轮验证

| 检查 | 结果 |
| --- | --- |
| pnpm --dir packages/ui typecheck | 通过，源码/预览/TSX 测试 |
| pnpm --dir packages/ui build | 通过，dist JS/d.ts/CSS；没有 Next build |
| pnpm --dir packages/ui test | 13 passed，0 failed，含既有导出、固定 tokens、禁用原因、unknown、POST markup |
| pnpm --dir packages/ui test:no-js | 1 passed，0 failed；原生表单协议 + loopback 安全拒绝夹具；不保存 body |
| 浏览器状态/交互 | 9 组：入口、readonly/capability、unknown、pending/error、真实展示回调、模态关闭约束、双向焦点、表格状态、无脚本原生提交 |
| 双向焦点 | 8 次 Tab + 8 次 Shift+Tab 均留在弹窗；关闭恢复触发按钮 |
| pending 负向验证 | Esc 不关闭，关闭按钮 disabled，原生 method=dialog 提交不关闭且子提交回调未执行 |
| 1440/1920/2560/390 ×1000 | 无整页横向溢出；390px 表格容器341px、内部760px，三入口始终保留 |
| 最终浏览器日志 | 0 warning/error |

无脚本浏览器页直接由同一 LoginPanel SSR 生成，没有 script 标签，并用 CSP script-src none 禁止脚本。使用虚构凭据原生提交：实际请求 POST /api/v1/auth/login，query_present=false、credential_query_present=false，body仅计59字节不保存。显示415拒绝页面；提交地址无查询串；可读取的测试历史 URL 无密码，后退回原登录地址。响应正文未回显密码。它证明本组件回退行为，不证明实际 Auth 路由的密码安全。

首次新增 markup 测试因假设 HTML 属性顺序失败，已改为独立检查 method/action；回归通过。无脚本 HTTP 测试在默认沙箱被 loopback listen EPERM 阻止，经过工具审批后执行通过，不把首次失败隐去。

浏览器证据只写在包内忽略目录 packages/ui/var/ui0-evidence/：browser-checks.json、states-desktop.jpg、mobile.jpg、pending-dialog.jpg、no-js-rejection.jpg。提交的 UI0-VALIDATION.json 记录这些证据的 hash，图片和生成数据不进 Git。

## 复现

在原 website Worktree，使用主仓库只读 Node24.22.0 工具链和既有包内依赖：

```sh
pnpm --dir packages/ui typecheck
pnpm --dir packages/ui build
pnpm --dir packages/ui test
pnpm --dir packages/ui test:no-js
pnpm --dir packages/ui preview -- --port 3250
pnpm --dir packages/ui preview:no-js -- --port 3251
```

3250 是本地展示预览；3251 只接受/拒绝虚构表单，不调用 Auth。它们不注册为生产服务。脚本修改后重启预览并刷新，不依赖 HMR。

未验证：clean checkout/workspace frozen-lock 安装与 B0 build 登记、实际 Next 组合、真实 Auth/权限/CSRF/API/SSE/来源心跳、完整跨浏览器/屏幕阅读器、生产部署。新包 importer/root lock 仍由 B0 处理，本包隔离依赖成功不能替代该门槛。所有后端批次仍由总管单独放行。
