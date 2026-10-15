# 第二阶段公共组件和独立 UI

版本 `phase2-v1.0.0`。已有公共 UI 候选固定为 `4527ba4510dcb3ea8a3d1bf932dc46367070d1d5`，作为展示组件接口与设计的起点；不在本轮合并该提交。组件 owner 为“全站UI设计”，三个业务页面由各自 UI owner 持有。

## 共享边界

公共组件只渲染 props、触发 callbacks、处理键盘/焦点与可访问状态。不请求 API、不保存账号/业务数据、不实现身份、重试、监控、Wallet、RPC 或数据库。每个操作必须有回调或明确的 disabled/unsupported 原因，不能模拟 live 成功。

保留公共导出：Icon、Button、Input、Select、SearchInput、Badge、ScoreBadge、Panel、PageHeader、Toolbar、AppShell、DataTable、Dialog、Alert、EmptyState、ErrorState、Skeleton、ToastViewport、LoginPanel、AccountSummary。Props 的非兼容变更需总管审阅；页面不得复制公共实现另造第二套组件。

| 组件 | 冻结规则 |
|---|---|
| AppShell | 只有三个业务入口 /、/hunter、/tracking；账号链接默认 /auth，登录 /login；页面不能嵌套两个 shell |
| DataTable | columns/rows/rowKey，sort/onSortChange，loading/refreshing，empty/error；稳定唯一 rowKey；一页最多100条，cursor由领域层持有 |
| SearchInput | value/onValueChange、可访问 label；Esc/清除回传空值，不自己加 debounce/API请求 |
| ScoreBadge | grade 与 ProjectRating 同为 S/A/B/C/D/null；null 显示未评分；可选数值仅来自明确数据，不由等级推算 |
| Button | 原生 type 默认 button；pending 禁用重复提交；业务提供操作结果，不内建副作用重试 |
| Dialog | 受控 open/onOpenChange，Esc、Tab/Shift+Tab focus trap和关闭后焦点恢复；破坏性操作默认取消焦点；pending不能绕过关闭约束 |
| Alert/ErrorState | 展示公开 code/message/request_id；onRetry是回调，不显示raw错误/私有payload |
| LoginPanel | onSubmit、pending/error/disabled；字段 username/password；必须显式 method=post、固定同源 action，脚本失效不得GET密码 |
| AccountSummary | 身份与能力来自真实AuthSession或标明的demo，不实现账号CRUD、不持有密码/session |

依赖版本沿用基础 Node24.22、React19.3.1、TypeScript5.9.3；新依赖、root lock、root构建顺序只由总管另行候选登记。UI 当前可在自己的 package 内按已冻结版本做隔离测试，不得以绕过 workspace安装的成功代替未来 clean checkout/frozen install验收。

## 视觉和页面适配

沿用全新 UI 候选的系统字体、13px 表格、4px间距、冷灰背景和青绿色主操作；不依赖外部字体。固定 tokens：页面 #0b0e12、面板 #111820、边框 #293544、主字 #e8eef5、次字 #a6b4c5、主操作 #8ce4c2、错误 #ff9caa。主侧栏216px，桌面内容24px内边距；表格横向滚动限于自己的容器，不能撑宽整页。

三页面只写自己的 features/components/prototype 路径，以同一phase2 DTO为输入约定。snake_case DTO→页面视图模型的纯转换允许由页面 owner 完成，但不能生成业务 ID、补监控逻辑、打开DB或创建登录。真实API adapter由领域 owner提供，页面用 props/callback 注入，模式明确为 demo/live。

原Worktree尚无新增phase2共享类型，因此UI0先使用本页面的纯view-model类型并按DTO逐字段对应；公共类型import/依赖传播由B0登记，不可用绝对路径import主仓库、跨Worktree可写链接或偷改root lock来解决。公共组件源码不能复制；依赖它的页面交付可先保留独立组件插槽/props，待获授权的组合验收绑定唯一@ikun/ui实现。

仅demo可含虚构项目/模拟权限/本地存储/计时器，必须持续标记；真实请求失败不能回落演示数据。live默认 capability=false，不把command accepted/202、health ready或SSE在线显示为监控成功。unknown展示“结果待核实”，不提供盲目重复写入按钮。user保留读取，不显示可执行业务写入；服务端仍要再验权。

主页使用 ProjectRecordV2：home_membership与progress_stage/percent分开，rating含null，未知时间留空。Discovery短ID与canonical项目ID分开；Tracking subscription_id与project_id分开。主页移除与监控移除是不同确认文案，禁止“删除项目同时停止监控”的默认组合操作。

UI实际网络/业务接线仍暂停。已有 /tracking 演示路由与其他预览只能作隔离候选，发布候选不得包含默认可访问的模拟写按钮、样例账号或真实Hunter身份。全站layout/globals/rootpage/proxy由总管保留，不由UI窗口覆盖。

## UI0 验收

必须提供新的commit、仅本窗口文件、clean状态、共享文件无越界diff。公共组件做typecheck/build与关键交互检查；三个页面做自己的typecheck与浏览器交互，1440/1920/2560及390px验证整页无横向溢出、表格内部滚动、加载/空/错误/刷新保留旧数据、键盘焦点、取消/重复提交防护。

含密码的展示组件或表单必须有脚本关闭/事件未绑定的回归：地址栏、请求URL、历史中没有密码；固定POST失败可见且不外发。使用虚构凭据，不填真实密码。没有测试证据就标未验证。

三页面支持通过注入回调演示拒绝权限、超时、409冲突、pending、unknown、成功；只做显示，不能为了通过UI验收复制领域引擎。各窗口交接列出字段转换、依赖和尚缺的live adapter。
