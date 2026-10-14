# @ikun/ui

ikun.ca 公共视觉组件候选。设计与交互规范见 [DESIGN.md](./DESIGN.md)，集成边界与验证证据见 [HANDOFF.md](./HANDOFF.md)。组件不发请求、不访问数据库、不实现监控或认证。

## 在当前候选 Worktree 运行

基础锁文件尚未登记新 UI 包。先安装基础依赖，再只安装包内开发依赖；不会修改根 lockfile，也不创建第二个 Git 仓库。版本均已固定，与基础版本一致；esbuild 已存在于基础锁文件的 tsx 传递依赖中，此包将其作为预览工具直接声明。

```sh
export PATH="/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH"
cd /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/website
# 基础依赖安装须在复制新 packages/ui 之前执行；当前 Worktree 已完成。
# pnpm install --frozen-lockfile
pnpm --dir packages/ui install --ignore-workspace --lockfile=false --store-dir "$PWD/.pnpm-store"
pnpm --dir packages/ui typecheck
pnpm --dir packages/ui test
pnpm --dir packages/ui build
pnpm --dir packages/ui preview -- --port 3250
```

预览地址为 `http://127.0.0.1:3250`；只监听 loopback，Ctrl+C 退出。端口可用 `--port` 调整，范围 1024–65535。预览只保存当前 React 内存状态，刷新清空；全部内容标为示例，无业务 API、登录或数据库。预览没有 HMR，修改源码后重启并刷新。

根锁文件由总管集成更新后，统一用 `pnpm install --frozen-lockfile` 和 `pnpm --filter @ikun/ui build/typecheck/test`。本候选不修改根包、根脚本、Next 配置、其他窗口页面或根锁文件。

## 消费方式（总管集成）

1. 给网站声明 `"@ikun/ui": "workspace:*"`，总管更新根锁文件。
2. 先 `pnpm --filter @ikun/ui build`，再构建网站；exports 指向 dist，无需运行时转译 TSX。加入总管统一 build/typecheck/test 流程。
3. 根 layout 只引入一次 `import "@ikun/ui/styles.css"`。清理根 CSS 中会覆盖 UI 的全局 button/input/table 规则；由总管处理，不在候选中改根 CSS。
4. 一个页面只有一个 AppShell。由稳定的客户端入口调用 usePathname，将 Next Link 通过 LinkComponent 传入。导航中只放三个固定业务入口，账号链接属于底部账号区域。
5. 三个业务窗口只使用自己的路由、请求层和状态；不用 UI 预览里的示例数据作为业务 fallback。

```tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppShell, PageHeader, Panel } from "@ikun/ui";

export function WorkspaceFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return <AppShell pathname={pathname} LinkComponent={Link}>
    <PageHeader title="页面标题" description="业务窗口提供说明" />
    <Panel>{children}</Panel>
  </AppShell>;
}
```

认证窗口在真实 auth/me 返回后提供 account。权限遵循最新总管 HANDOFF：superadmin 写入，user 只读。UI 的角色文字与 disabled 不能替代服务端授权。登录页独立使用 LoginPanel，不嵌套 AppShell。

## 组件 API

| 组件 | 核心参数 / 行为 |
| --- | --- |
| AppShell | pathname、children、account、footer、LinkComponent；固定三入口、底部账号、skip link |
| PageHeader / Panel / Toolbar | 标题、说明、actions / children；统一页面层级与筛选布局 |
| Button | variant primary/secondary/ghost/danger；pending 防重、size sm/md、原生按钮属性；默认 type=button |
| Input / Select | 必须 label；hint / error 自动关联；原生 value/onChange/required/disabled |
| SearchInput | label、value、onValueChange；Esc 与清除按钮回传空字符串，不实现 debounce |
| Badge | tone neutral/success/info/warning/danger；文字由业务提供 |
| ScoreBadge | grade S/A/B/C/D/null，value 0–100/null；不推算等级 |
| DataTable&lt;Row&gt; | caption、columns、rows、rowKey；sort/onSortChange，loading/refreshing，empty/error；minWidth 默认 760 |
| Dialog | open/onOpenChange、title、description、footer、pending；closeOnBackdrop 默认 false；initialFocusRef 可指定焦点 |
| Alert / ErrorState | title、说明、requestId；ErrorState 的 onRetry 只触发调用方回调 |
| Skeleton / EmptyState | label / title、description、action；加载与空状态独立 |
| ToastViewport | messages、onDismiss；success/info/neutral 5 秒关闭；warning/danger 保留；业务应限制数量 |
| LoginPanel | 必须 onSubmit；pending/error/notice/footer/disabled；字段名 username/password |
| AccountSummary | name、identifier、roleLabel、statusLabel、statusTone、actions、children；不实现账号 CRUD |

DataTable 的 sortable 仅在提供 onSortChange 时启用。调用方提供稳定且唯一的 rowKey；金额使用字符串并由业务格式化，避免浮点损失。地址与数字使用 `ik-mono`。表格详情用独立链接/按钮，不以整行点击替代键盘入口。DataTable 没有虚拟滚动；遵循接口单页最多 100 条，额外分页由业务持有 cursor。

LoginPanel 的 onSubmit 得到阻止默认提交的 FormEvent。调用方可立即读取 FormData 并调用同源认证 API；业务负责 pending、错误、timeout、AbortController 和服务端校验。组件不读取、持久化或记录密码。禁止把事件对象异步保存为任务数据。

Dialog 使用受控 open；父层 onOpenChange 处理未保存修改。破坏性操作把 initialFocusRef 指向取消按钮并提供明确对象名称。pending 为 true 时阻止 Esc、关闭按钮及背景关闭。不要使用 form method=dialog 绕过受控关闭逻辑，不嵌套模态弹窗。

CSS 类全部置于 `.ik-theme` 下。独立组合组件需包裹 `<div className="ik-theme">`；AppShell、LoginPanel、Dialog 和 ToastViewport 自带 theme。公开辅助类：ik-stack、ik-actions、ik-mono、ik-muted、ik-hint、ik-panel--table。在业务类中引用 `var(--ik-*)`，不重新定义全站配色。
