# 全站 UI 候选交接 · 2026-10-15

状态：公共组件与设计规范已完成本地验证，等待总管集成审阅。未合并、未部署。三个业务页面和认证/监控业务属于各自窗口。

## Git 与范围

- Worktree：`/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/website`
- 分支：`codex/website`
- 基线：`f89d8f55fc3e68d6360e7a1e33e23bde48591098`（foundation-v0.1.0）
- 候选提交：通过 `git log -1 --format=%H -- packages/ui` 定位；本文件包含于候选，不嵌入自身提交 SHA。
- 源码、测试、文档和预览均位于 `packages/ui/`；根配置、根锁文件、contracts/runtime 源码、网站页面、认证模块、监控脚本、数据库均无修改。
- 已读总管 AGENTS / HANDOFF / GIT / OWNERSHIP / ARCHITECTURE / API / DEPLOYMENT。以最后 HANDOFF 的 superadmin/user 权限为准。

## 交付

统一深色 tokens、字体、数字/地址、间距、小圆角、按钮、搜索、输入/选择、评分、状态、表格、弹窗和通知。包含三入口 AppShell、登录表单和账号信息展示组件。具体交互与布局见 DESIGN.md，使用参数与集成步骤见 README.md。

组件只接收 props 并触发回调；没有网络请求、数据库驱动、Watch、SSE、监控轮询、业务存储或认证实现。预览数据标记为示例，操作只修改预览 React 内存；登录提交明确返回“认证服务未接入”。

## 总管需要协调的集成项

1. 新 workspace 包 `@ikun/ui`：根 lockfile 尚未登记 importer；当前不可对新包宣称统一 `pnpm install --frozen-lockfile` 已通过。请在干净集成 Worktree 更新根锁文件。包开发依赖固定为基础已有版本，esbuild 0.28.2 从原传递依赖变成预览工具的直接开发依赖；生产组件只需要 react/react-dom peer。
2. 网站 package.json 增加 `@ikun/ui: workspace:*`；build 顺序先 UI 再网站；统一检查增加 UI 的 typecheck/test。根 layout 导入一次 styles.css，并处理根 CSS 的全局覆盖规则。候选未改上述共享文件。
3. 页面路由建议 `/`、`/hunter`、`/tracking`，辅助路由 `/login`、`/account`；请向三个 UI 窗口统一。该路由建议是视觉集成项，未变更 /api/v1 契约，也没有创建实际业务路由。
4. 各业务页由自己请求层传入 loading/refreshing/error、分页 cursor、排序结果、评分和真实来源心跳状态。不得用预览数据作为 fallback；不从 ready 推断 connected。
5. 认证窗口负责真实会话、superadmin/user 权限、错误映射和写入校验；AccountSummary 的 roleLabel 只是文字，不是授权判断。未接入操作禁用并说明原因。

## 实际验证

使用主仓库只读 Node 24.22.0 工具链，所有依赖安装在本 Worktree。先按基础锁文件安装六个包，再对 packages/ui 使用 --ignore-workspace --lockfile=false 的独立开发安装；没有修改根锁文件，也没有复用其他窗口 node_modules/var。

| 命令 / 检查 | 结果 |
| --- | --- |
| pnpm --dir packages/ui typecheck | 通过，包含源码、预览与测试 |
| pnpm --dir packages/ui build | 通过，生成 dist JS / d.ts / CSS；保留 use client |
| pnpm --dir packages/ui test | 10 passed，0 failed |
| pnpm build:shared | contracts/runtime 构建通过；仅生成忽略的 dist |
| 浏览器交互 | 11 组检查通过，见下表；最终标签页无 warning/error 日志 |
| 视口 | 1440 / 1920 / 2560 / 1024 / 390，height=1000；均无整页横向溢出 |
| 对比度 | 主/次/辅助文字对三种底色均 ≥4.5:1；输入控件边框 ≥3:1；按钮和语义标签文字 ≥4.5:1 |

| 浏览器检查 | 结果 |
| --- | --- |
| 三业务入口导航与 active 路径 | 切换到 /hunter，仅一个业务链接 aria-current=page |
| 搜索与 Esc 清除 | north 过滤至 1 行，Esc 恢复 4 行 |
| 表格排序 | 评分升序的第一行是 73 分示例，aria-sort=ascending |
| 刷新失败 | 错误提示出现，4 条已有数据保留 |
| 显式重试 | 错误区域关闭，切换到加载完成示例 |
| 首次/后台加载 | 首次显示骨架，后台显示更新中并保留 4 行 |
| 弹窗焦点与 Esc | 打开焦点进入，Esc 关闭后回到触发按钮 |
| 弹窗提交与通知 | 备注在预览内存保存，成功通知出现 |
| 登录 | 密码显示切换；提交显示未接入，未调用认证服务 |
| 账号 | 状态显示未接入，退出登录禁用 |
| 双向焦点循环 | 连续 8 次 Tab + 4 次 Shift+Tab 均在弹窗内 |

视口实测：桌面侧栏 216px；1024px 下图标轨道 72px；390px 下顶部三入口，表格容器 341px / 内部内容 760px，整页未被表格撑宽。每次设置尺寸后等 DOM/布局状态，再读取宽度。

验证中修复：tsx CLI 的 IPC 管道受沙箱限制，测试改用 node --import tsx 并显式指定 tsconfig；内嵌浏览器原生 dialog 在最后一个控件 Tab 时可进入浏览器区域，已增加组件首尾焦点循环，双向复验通过。

本地证据位于忽略目录 `var/ui-evidence/`：browser-checks.json、components-desktop.jpg、components-mobile.jpg、login.jpg、account.jpg、dialog.jpg。截图与数据都是此包的合成示例，不包含账号/监控/生产数据，不提交生成图片。

## 运行与限制

```sh
export PATH="/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH"
cd /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/website
pnpm --dir packages/ui preview -- --port 3250
```

当前组件预览只监听 127.0.0.1:3250；不是正式三服务之一，正式发布无需启动它。使用 Ctrl+C 或向这个预览进程单独发送 SIGTERM 关闭，不操作其他窗口进程。

未验证：三业务页实际接入、Next 网站集成构建、真实认证/权限/API/SSE、真实来源心跳、生产部署、屏幕阅读器、跨浏览器矩阵。浏览器结果来自本机 Codex 内嵌浏览器；对比度与语义检查不等于完整可访问性认证。没有旧版复制、旧服务重启、Watch 修改、数据库读写、付费或链上动作。
