# 登录系统 B1 放行条件

当前结论：B0基础设施验收通过；**登录系统仍held，未获开工、主站接入、合并或部署许可。** 本文列准入条件，不是一封放行通知。认证候选固定为aa3cf65ce5c24cc293e0daec279659d2cc080c5f，原Worktree为../ikun-ca-v2-worktrees/auth、分支codex/auth。

## B1 开工前必须满足

1. 总管的B0验收记录、固定基础设施tag与规范可读取，来源/hash及文件白名单通过check-b0。四个UI最终稿保持冻结。
2. 用户明确放行“登录系统B1”的本地修复与适配。当前用户要求后端业务继续冻结，因此本项尚未满足；B0通过不自动放行B1。
3. 在原Auth Worktree从上述冻结SHA另做新提交，保留失败记录；不得amend/reset冻结提交、重复做一套认证或复用旧版账号/数据库。
4. 范围仅modules/auth/**、schemas/auth/**及本模块integration候选。预览可在本模块ignored临时目录读取固定B0源码构建测试；不直接改主仓库/其他Worktree，不改root依赖/锁、公共UI、proxy/layout/globals或业务worker。正式路由/依赖/支持版本的收件由总管按receiving-plan另审，合并与生产仍需单独授权。

已知P0和失败测试是**获准开工后的首要修复与验收任务**，不是要求冻结窗口在放行前自行改代码。

## B1 完成后必须验收

| 门槛 | 必须提供的证据 |
|---|---|
| 密码表单P0 | static/login.html、password.html、users.html及生成src/ui.ts全部使用显式同源POST和固定action；无JS/未绑定脚本时虚构密码不进入URL、历史、日志或响应。只支持JSON时原生表单应安全拒绝，不得退回GET。公共LoginPanel已通过的测试不能代替本模块测试 |
| 最终代码回归 | aa3cf65已有33个最终测试完整复跑，加上修复新增回归；绑定新完整SHA，不能引用早期31项或旧Python候选结果 |
| Next/浏览器 | 隔离Next完整构建；复测曾失败的390px重置密码流程及登录/首次改密/用户管理/退出，记录1440与390布局、键盘及所有实际失败，无JS表单也需浏览器证据 |
| 可信身份 | 固定ikun-main、仅superadmin/user；capabilities由服务器计算。匿名拒绝、user业务只读、superadmin写；不信客户端role/scope/转发身份。强制改密期间拒绝业务 |
| 协议对齐 | /auth/me补齐AuthSessionV2的capabilities；用户列表投影为PageV2；reset-password使用new_password，用户PATCH白名单、退出和本人改密响应与phase2 DTO逐项对齐。现有字段不能静默冒充新字段；如需契约修订，先交总管审阅，不自行修改共享规范 |
| 会话与权限 | 禁用/改密/重置/降级撤销；每请求重验；Cookie/Host/Origin/CSRF/限流/最后管理员并发保护；SSE建连、数据与静默期间持续撤销并取消上游。仅页面隐藏按钮或SSE连通不算通过 |
| 四库与迁移 | 只写auth/auth.db；保留foundation1，显式002迁移/重启/失败回滚/校验和错拒绝。对齐唯一迁移权威与_migration_checksums，保留已有auth_migration_checksums记录的兼容/迁移证据；不得清库重跑掩盖问题 |
| 运行接入 | Auth仍在website内，不增独立服务。B0默认maximumVersion=1，Auth2只在获准的预览/收件补丁中明确声明支持2并验证自己的checksum/scope；不能全局放宽版本或让HTTP readiness迁移 |
| 交付 | 新SHA、规范版本、diff白名单、复验命令/结果和剩余限制；git diff --check与原hook都通过。原冻结提交末尾空行问题可在新提交中修正，不能改写冻结历史 |

## 可复用的验收基线

本轮只静态核对Auth源码与FREEZE，没有运行或修复冻结业务。已观察到sessionData缺capabilities、users返回{users}、重置收password、PATCH仅enabled；这与phase2 DTO不同。具体新增适配以规范和获准范围为准，不为适配而削弱原会话/权限保护。

B1完成后也只是认证候选通过，不能据此宣称真实Projects/Hunter/Tracking读写、Cloudflare、公网登录或生产验收完成。当前本地B0根站业务接口仍503/501。
