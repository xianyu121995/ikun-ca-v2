# 第二阶段正式放行和验收

规范版本 `phase2-v1.0.0`。每项验收必须绑定完整commit、规范版本、允许文件、命令/结果与未验证项；不能把冻结、构建或fixture通过写成正式功能验收。

## 可以立即开工

**全站UI设计、主页UI设计、猎手监控UI设计、猎手项目监控UI设计。** 仅按 UI.md 和 OWNERSHIP.md 在原Worktree做公共展示组件、不冲突的页面/纯视图适配、回调和UI测试。全站UI先固定公共接口；三个页面可同步做各自布局、错误/readonly/pending/unknown状态与纯adapter，依赖共享接口的修改等待UI owner交付，不复制组件实现。8GB机器构建串行。

本次没有放行后端功能修改、全站接线、分支合并或生产部署。三个曾未冻结窗口的收尾提交均已完成，进入以下候选基线，不能继续扩展原任务。

## 后端批次

| 批次和窗口 | 前置门槛 | 本批必须验收 | 当前状态 |
|---|---|---|---|
| UI0 四个UI窗口 | 冻结规范、自己的路径 | UI.md矩阵、共享接口/字段、密码表单no-JS安全、无业务实现/越界文件 | 已放行 |
| B0 项目总管 | UI0交付审阅；另行明确放行基础设施修改 | root锁与build登记；fresh冻结依赖；三服务受托管生命周期/私有IPC；迁移explicit columns/四列兼容；只读readiness/唯一writer | held，本轮不修复 |
| B1 登录系统 | B0验收通过并记录放行 | 修复密码GET P0；最终完整权限回归/浏览器；匿名拒绝、user业务只读、superadmin写、禁用/改密/重置撤销、CSRF、scope、SSE持续撤销；只写auth.db | held |
| B2 再做项目管理 | B1可信身份契约与B0 IPC通过并记录放行 | 沿用已有项目逻辑；网站受托管组件，无第四作业/公开端口；移除独立用户会话来源；canonical/来源去重、hidden/active/removed、完整DTO、cursor/ETag/幂等、明确加入/receipt/outbox、删除不影响监控 | held |
| B3 猎手项目监控跟踪 | B2canonical解析和命令/receipt协议通过并记录放行 | subscription与project ID映射；方向服务凭据+可信actor；单scope；commands/inbox、remote核验、去重、unknown reconcile、迁移与restart；不写别库、不启真实共享Watch | held |
| B4 猎手监控 | B3接收命令/回执通过并记录放行 | 固定scope、标准公开DTO/BFF权限、72h/generation/baseline、脱敏、人工confirmed事件、outbox→回执/reconcile；网站关闭继续；不复制改写现有引擎 | held |
| C0 集成验收 | B4及所有候选独立验收通过；合并另需明确授权 | 先按最终SHA/hash更新工具收件；组合真实Auth→发现→确认→订阅→推文→主页数据；区分加入监控/主页、权限、跨库删除、单进程崩溃/断线恢复、fixture/真实平台分别证明 | held；禁止合并 |
| D0 发布审查 | C0完整通过；用户批准发布动作 | 三launchd服务、8GB压力/限流、四库backup/restore、日志轮转、运行路径、HTTPS/Access、rollback、独立凭据；域名/停旧服务逐项授权 | held；禁止生产部署 |

表格是严格依赖顺序，完成前置不能自行启动后续批次。总管记录具体SHA、验收证据、准入范围和放行时间后再通知该窗口；只有总管能改 releases.json，本文件不产生自动许可。需要领域SQL/接口变更只在放行批次适配已有成果，不开发第二套功能。

## 既有候选的验收限度

source-freeze.json记录9个源码提交。Hunter bd69bbd保留自动审批拒绝的最后硬化动作，未执行；Auth aa3cf65保留最终33项未复跑、浏览器失败、diff格式检查失败与密码表单P0；Integration c4845f5的基础/工具验证不能代替全站业务。规范冻结没有修复这些问题。

所有批次交付必须clean Git、只包含owner路径、无DB/secret/运行文件、hook检查、不隐藏失败。只用隔离目录/临时DB/loopback/MockTransport验收；真实平台只在后续独立授权中执行，不在UI0或冻结阶段触发。
