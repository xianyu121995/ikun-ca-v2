# B1 最终版：Next.js 登录与权限

本模块按用户最后确认的 B1 指令修订，替代 `48d9dd4` 的网页账号管理方案。独立 Worktree `codex/auth`；仅修改 `modules/auth/**`，没有改共享包、锁文件、业务库、worker、主站根文件或生产服务。代码复用既有 Argon2id、安全会话、CSRF、限流、统一鉴权与迁移校验；所有正式运行代码为 TypeScript，嵌入 Next.js 的 Node 进程。Python 只作 Chromium 测试驱动。

登录和改密页面直接消费固定公共 UI `486294ac3255b08fdb13a307ee15f96c571020d9` 的 `LoginPanel/Input/Button/Panel/AppShell/Alert`。没有网页账号管理后台或管理 API。主站收件候选在 `integration/website/`，技术总管负责审阅和接入；`integration/preview-only/` 仅为验收夹具，不能部署。

## 本地编译与账号命令

使用 `.node-version` 的 Node 24.22；现有 Worktree 的独立依赖，不增加依赖。

```sh
pnpm exec tsc -p modules/auth/tsconfig.json
# DATA_ROOT 必须是本部署专用的绝对路径；只会打开其中 auth/auth.db。
export DATA_ROOT="/absolute/private/path/to/site-data"
node modules/auth/dist/src/cli.js bootstrap --username your_admin
node modules/auth/dist/src/cli.js create --username reader_name
node modules/auth/dist/src/cli.js list
node modules/auth/dist/src/cli.js disable --username reader_name
node modules/auth/dist/src/cli.js enable --username reader_name
node modules/auth/dist/src/cli.js reset-password --username reader_name
node modules/auth/dist/src/cli.js recover-admin --username your_admin
```

所有账号命令必须在本机 TTY 运行，密码两次隐藏输入，不支持密码参数、环境变量或管道。不支持 `--role`、删除或角色修改；`create` 只能生成普通用户。`bootstrap` 仅创建一次超级管理员，新建包括初始超级管理员均强制网页改密。`recover-admin` 不依赖网页登录或旧密码，仅接受现存超级管理员；恢复启用状态、撤销全部旧会话、设置初始密码并强制改密。只有本机授权 OS 用户和 auth 目录访问权限是本地恢复的信任边界；拥有这些权限的人可以管理账号。

`list` 仅显示 user_id、username、role、enabled、must_change_password、revision。禁用/启用幂等，启用不恢复旧会话。重置普通用户不会自动启用；初期只允许一个有效超级管理员，最后一个有效超级管理员不得禁用。数据库角色列没有单管理员 UNIQUE，保留未来多管理员设计；当前命令没有创建第二管理员的入口。

独立迁移：`node modules/auth/dist/src/cli.js migrate`。迁移可以非交互运行；其余命令严格要求 TTY。除 bootstrap/migrate 外不创建或迁移数据库。迁移方案保持 schema 002 和历史 checksum，不重建、不清库；旧表及迁移回执保留兼容。

## 安全与会话

- 仅 superadmin/user。匿名业务 API 401，user 写入 403；must_change_password 在服务端阻止全部业务页面/API/Server Actions。普通用户只可访问显式只读业务清单和本人的会话/密码接口。
- Argon2id：64MiB、3 次、parallelism 1、随机盐；密码 15–128 Unicode 字符且最多512 UTF-8字节；最多4个异步哈希，超限429；新旧密码不得相同。
- 256 位随机令牌，DB 仅存 SHA-256 token hash。默认7天绝对有效期，访问不延长；配置及认证均强制最长604800秒，不因配置或旧 expires_at 放宽。允许部署收紧，绝不超过7天。最多5个设备。
- 退出撤销当前会话；禁用/重置/本地恢复撤销该账号全部会话。本人改密必须验证旧密码，在同一事务中撤销全部旧会话并生成唯一新会话；当前浏览器收到新 Cookie/CSRF，不要求重复登录，其他设备立即失效。首次改密亦采用此流程。
- 每请求重验 enabled/version/role/强制改密/过期；不采纳浏览器 user/role/scope。SSE 每块和静默期间每秒重验，撤销时关闭并取消上游。
- Cookie：生产 `__Host-ikun_session`，HttpOnly、Secure、SameSite=Strict、Path=/、Max-Age=604800，无 Domain。开发只允许 loopback HTTP；`IKUN_AUTH_DEV=1` 时使用独立开发 Cookie。
- Origin/Host/JSON/CSRF token 校验；密码表单固定同源 POST，无 JS 时415安全拒绝，不将密码放URL。请求16KiB/5秒上限。持久账户/IP/全局限流10/30/300次每15分钟（包含成功尝试），不会因重启清空；不信任伪造转发IP。生产入口可额外限流。
- 目录0700/DB0600，拒绝软硬链接、外来库、错误scope/checksum/未来schema。请求与 readiness 不执行DDL。不记录密码、Cookie、token或请求体。错误提示统一，不泄露账号存在/禁用状态。

生产要求 `IKUN_AUTH_ORIGIN=https://ikun.ca`，**移除** `IKUN_AUTH_DEV`，由正式 HTTPS 入口提供 TLS；不得将认证凭据放 `NEXT_PUBLIC_*`。auth.db 仍处 `DATA_ROOT/auth/auth.db`；三个业务库完全不导入、不打开。

## API 和业务接入

见 [INTEGRATION.md](INTEGRATION.md)，包含 Route Handler、Server Action、页面、SSE、公共 UI 和协议变化。只保留 login/logout/me/password 及狭窄的跟踪 session 兼容端点；任何账号管理端点始终404，即使 superadmin 也不能调用。`/auth/users` 同样404，`/auth` 只转本人改密。

## 自动化与隔离 Next 验收

```sh
pnpm exec tsc -p modules/auth/tsconfig.json
node modules/auth/scripts/prepare-preview.mjs
node modules/auth/scripts/build-preview.mjs
node --test --test-concurrency=1 modules/auth/tests/*.test.mjs
IKUN_NODE="$(command -v node)" IKUN_TEST_CHROMIUM="/path/to/chromium" \
  modules/auth/.venv/bin/python modules/auth/tests/browser_smoke.py
```

预览从固定 B0 `85be3bd6dce25d82033b6cb1a7157aaa39bd571e` 和公共 UI Git 对象导出到本模块 ignored 新目录，以私有 cache 离线/frozen 安装并串行构建。测试只启动临时 loopback `next start`、临时 auth.db，无业务库、生产连接、外部 provider 或新增常驻服务。测试结束停止自己的服务并清理自己的临时数据。结果见 `B1-REPORT.md`，不能用模块夹具替代主站业务/Cloudflare/生产集成验收。
