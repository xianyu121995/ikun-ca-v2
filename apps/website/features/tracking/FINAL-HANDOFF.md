# 猎手项目追踪 · UI 定稿交接

仅页面 UI 完成；默认只读、显式 demo、没有业务网络或数据库接线。延续分支 `codex/tracking-ui`，保留前一候选 `a6bebb39435fa02df9d9065df148e6fe2f0851f7`，本轮另提交。

## 定稿来源

- 文件：用户提供的 `ikun-hunter-project-tracking-ui-prototype (2).html`。
- SHA-256：`80a136cfbc5597a91a9a1f281c741de4503b44df7f8e20255decf869b30ed82a`；原文件未修改。
- `evidence/reference-layout.json` 记录原型1440/1920/390px的五张统计卡、每页六条、备注优先及初始隐藏的管理窗口。
- 以本次用户定稿替换此前事件表方案：不渲染旧展开行、AI摘要、排序控件、暂停按钮、独立“监控管理”入口或测试控制台。

## 实现和复用

- `final/tracking-page.tsx`：静态统计、筛选和分页、备注优先推文、媒体与互动数据、右侧账号管理及删除二次确认。
- `final/model.ts`：纯展示模型与搜索/评级/时间/重要筛选、发布时间倒序、每页6条、北京时间统计、表单校验。未知发布时间不补当前时间，限定时间范围时排除未知和未来时间。
- `final/demo-data.ts`：10账号、12条原型虚构推文和指标；所有媒体是本地示意卡，无第三方资源。支持本地图片/视频展示类型，外部或脚本媒体地址不加载。
- `final/tracking-demo.tsx`：仅内存更新；`demo-local-*` 只是渲染键，不生成真实账号、项目或订阅 ID。添加不会合成推文；删除隐藏展示，不销毁传入历史。
- `tracking-workspace.tsx`：唯一公共 AppShell，使用公开 LinkComponent 插槽将本页导航显示为“猎手项目追踪”，不改公共导航源码或其他入口。
- 复用冻结公共包 `@ikun/ui` 来源 `4527ba4510dcb3ea8a3d1bf932dc46367070d1d5`；构建消费方式与前一候选相同。没有新增依赖、root lock 或公共源码修改。

## 行为边界

真实数据由未来接入方提供。Account/Post 是页面展示模型，不修改既有 phase2 公共传输类型；接入方需将已授权的项目备注、S/A/B评分、已追踪账号与推文/媒体映射进来。`ui_key` 不替代 canonical project/subscription 身份，不能按 handle 自动创建业务身份。

管理写入口目前只在明确 demo 且同时提供本地回调时可用；live 为只读。演示回调不是生产 API 适配器，不得直接用于绕过认证、revision、原回执查询或命令 pending/unknown 处理。后续真实写入和权限接线仍由领域 owner 与总管安排，本轮未实现。

删除按本次定稿只隐藏演示账号和关联信息流，不操作真实监控，也不表示删除项目或历史数据库。增加需填写用户名、名称、备注和评分，点击“确认添加（模拟）”；删除弹出独立确认，取消默认获焦，外层窗口在确认期间不可关闭。原文按钮明确提示演示无真实链接，不打开虚构 X 帖子。

## 验证与未接入项

验收命令见 README，结果为 `evidence/browser-results.json`、`evidence/validation.json`。覆盖原型结构、发布时间顺序、备注优先、六条分页、搜索与组合筛选、增删校验与取消/确认、焦点循环/恢复、HTML文本渲染、1440/1920/2560/1020/768/390/360px及抽屉内部滚动。

没有接真实 API、NEW_TWEET、SSE/WSS、认证、数据库或其他模块；没有 merge/push/deploy。公共包正式 workspace 登记和 clean checkout/frozen install 仍待 B0 完成。测试证明本页 UI 候选，不代表真实监控接入或生产验收。
