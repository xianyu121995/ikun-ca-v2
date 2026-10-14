# 项目监控模块交接 · 2026-10-15

状态：独立引擎、tracking.db、业务 API 与运行页面已实现；隔离验收通过。正式主站/UI 合并、独立 6551 凭证与真实远端验收仍未完成，不能宣称已上线或真实账号正在监控。

基础：`f89d8f55fc3e68d6360e7a1e33e23bde48591098` / foundation-v0.1.0。分支 `codex/tracking-worker`，仅 services/tracking-worker 与 schemas/tracking。主目录早期候选完整保留，未复制 DB、账号、secrets 或 venv 到 Worktree。没有修改任何其他窗口、根锁文件、contracts/runtime、旧版服务、Watch 或 Tunnel。

## 已验证

- Python 隔离测试 41 项：人工确认、鉴权/只读角色、CRUD/版本冲突/幂等、远端假成功、超时已生效回查、配额不足、接口故障、共享 Watch 所有权保护、重启恢复、事件筛选/去重/正文补全、REST 历史窗口缺口、真实 loopback WSS ACK/pong/断线重连。
- 进程测试真实结束网站进程，随后新推文仍入 tracking.db；重启网站能查回记录；SIGKILL 引擎后模拟租约过期并重启，不重复增加远端任务或推文。正常 SIGTERM 释放租约。vendor 为 loopback 模拟。
- 真实 Chrome：登录、添加、编辑、停止、恢复、移除待核验、搜索、只读权限、XSS 字符与 1440/390px 布局通过；未发现 pageerror。截图在忽略的 artifacts/，包含明确测试项目和离线状态。
- BFF、live UI adapter smoke；tracking-worker TypeScript typecheck/build；launchd plist 语法校验。现有 `scripts/service.mjs tracking start` 实际启动 API+引擎、外部调用关闭、SIGTERM 逐层退出码 0 的 smoke 通过。
- 一条 Starlette TestClient 使用 httpx 的弃用提示，无失败；没有用此提示掩盖未执行的测试。

## 需要总管审阅的集成差异

1. Python runtime opt-in 嵌入现有 tracking 服务：Node 入口无 IKUN_TRACKING_CONFIG 时保持 foundation idle；有配置时启动单一 Python API+engine。根依赖/锁文件未改。需要接受 Python 3.11、模块锁文件和发布 venv 方案。
2. `/api/v1/tracking/subscriptions` 实现规范化 ID、envelope、UTC、UUID 幂等、If-Match 和分页；启停与删除异步返回 202，远端核验结果另查。`/api/tracking` 仅为当前自有页面适配层。
3. 认证按最新 superadmin/user 规则，仅 superadmin 写。每次请求通过独立认证 API 验证 session，未读取认证库。当前是单站点资源集合，未实现 multi-tenant allowlist/隔离；若多租户是正式发布硬门槛，必须继续保持该集成阻塞，不能把本模块当成多租户实现。
4. tracking-ui 当前为 demo-only presentation contract。提供 LiveMonitorAdapter；正式 UI 需要接收 mode=live，提供人工确认后的 canonical project_id/name/handle，按 capabilities 禁用 demo/未支持按钮。已读、分类持久化、独立操作日志查询不在本次监控需求内，未伪造实现。
5. BFF 候选只转发所需 cookie/Origin/CSRF/版本头，不信任客户端角色、不嵌入服务或 6551 Token。必须在认证 API 路由不会回流 tracking 的网站组合中验收，防止 session 验证回环。
6. tracking 库使用 foundation application_id=0x494b0202，业务迁移版本 2，checksum 验证。只在服务启动或 init 迁移自己的库；基础身份不匹配、外库、软硬链接拒绝。旧二进制不能回滚覆盖此库，需保留兼容 release。
7. 正式服务内部 commands/event-outbox/跨租户 token 协议尚未实现；当前页面通过同源 API 拉取 tracking.db 的真实状态。未擅自补全 projects.db 导入或写入网站。

## 真实远端验收门槛

由用户在本地填写独立账号凭证文件，启用两项远端开关。先只读核对 Watch 返回形状、groupName 与全部事件 flags、名额，再用人工确认的测试项目完成真实 add→read→event→stop/delete→read→resume→read，以及断线恢复。缺少 groupName/flags 或列表不完整会安全阻塞，不能猜格式放行。此前共享 Watch 始终不操作。

不得使用本模块测试条数宣称主站已合并、已部署、真实 6551 事件已送达或长时间断线无遗漏。生产 launchd/路由模板仅为候选，未安装，未创建自动化。

本 Worktree 已创建忽略的可编辑 `services/tracking-worker/python/config.local.json`（3412，真实远端关闭）及空 `var/dev/tracking/tracking.db`。integrity_check=ok、foreign_key_check=0，0 个项目；没有后台驻留实例或真实监控账号。配置、DB、venv、截图均未纳入提交。
