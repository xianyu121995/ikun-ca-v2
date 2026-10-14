# ikun.ca v2 认证候选

所有者：登录系统窗口，`codex/auth`，基线 `f89d8f55`。正式实现为 TypeScript / Node 24.22，直接嵌入 Next.js 网站进程，**不增加第四个服务**，不增加 pnpm 依赖，不修改三个业务库。主目录中的早期 Python 候选保留原状，不属于本次正式实现。

**状态：认证模块与 Next 接入候选可本地验证，未合并主站、未部署。** 集成文件保存在 `integration/website/`；未覆盖其他窗口的 `apps/website`、共享 contracts/runtime 或锁文件。总管审阅后接入。生产不提供默认账号，不开放注册。

## 功能与安全

- 用户名/密码登录、退出、修改自己的密码。仅 `superadmin` / `user`；管理员可创建两种角色、禁用/启用、重置密码。普通用户不能修改业务数据。
- Node 原生异步 Argon2id，64 MiB、3 轮、并行度 1、随机 16 字节盐、32 字节输出；15–128 字符密码，不截断。最多同时 4 个哈希，超额返回 429/Retry-After。
- 256 位随机会话，数据库仅保存 token SHA-256 摘要；最多 5 个设备。生产 `__Host-ikun_session`，Secure / HttpOnly / SameSite=Strict / Path=/，无 Domain，不写浏览器存储。
- 12 小时绝对、30 分钟闲置过期；`me` 后台探测不续期。登录和改密换 token；退出撤销当前会话，禁用/重置/改密撤销全部旧会话。新建和重置后先改密，完成前禁止业务访问。
- 每请求重新验证身份、角色、禁用状态、会话版本；账号写事务内再次复查操作者。只读页面/API 必须显式声明；未知路由默认仅管理员，不能凭 GET 推断无副作用。业务 API 接入还需声明经过审计的读取清单。
- Origin + JSON + 同步 CSRF token；Host/方法覆盖校验；请求体实际流量上限 16 KiB、5 秒读取超时；统一 `data/error + request_id`，不回显密码或验证原始输入。
- 持久登录限流：用户名 10 次/15 分钟、可信直连来源 30 次/15 分钟、全局 300 次/15 分钟；成功也计数，重启不清空。Next 适配器不信任客户端转发 Header，默认按 ingress 聚合；边缘真实 IP 限流由入口补充。
- 用户管理写入 UUID Idempotency-Key，7 天保留；启用/禁用和重置还需要 If-Match。含密码请求的幂等校验也用 Argon2id，避免产生快速密码猜测摘要。禁止额外字段/第三种角色，保护最后一个启用管理员。
- SSE 包装器在每块数据和静默期间每秒复查，撤销/过期/存储故障关闭并取消上游；业务 SSE 接入时必须调用 `AuthHttp.stream`，仅在代理建连校验不足以持续撤销。
- 审计只记录事件、操作者和目标 ID，不记录密码、原始 Cookie/token。审计保留 90 天，过期会话、限流和幂等记录在登录尝试时清理。

密码和会话方案参考 [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)；实现核对 [Node 24 crypto.argon2](https://nodejs.org/download/release/v24.16.0/docs/api/crypto.html#cryptoargon2algorithm-parameters-callback)。UI 使用当前 v2 的深色、薄荷绿与表单样式，无远程字体/脚本。

## 独立 auth.db 与迁移

唯一打开路径是 `DATA_ROOT/auth/auth.db`。兼容基础标记 application_id `0x494b0204`、`_store_identity='auth'`、foundation 版本 1。迁移 002 新增 `auth_*` 表、迁移校验和及服务端 site scope。只提供本机显式 CLI 迁移；请求不运行 DDL，不接纳无 v2 标记的已有库。WAL、FULL、外键、busy_timeout=5000，目录 0700 / 文件 0600；拒绝路径及 WAL/SHM 的软/硬链接。

初始 `tenant_id=ikun-main`（可用 `IKUN_AUTH_TENANT_ID` 设置）；持久绑定账号库，配置与库不一致时拒绝启动。单站点账号全属这个 scope，不实现组织管理，不接受浏览器指定其他 scope。三个业务库和监控引擎不导入本模块。

迁移前对 **auth.db** 做 SQLite online backup 或停网站后完整备份；不在线只复制主文件遗漏 WAL。002 为新增表，无旧账号导入。失败事务回滚，可修复原因后重跑；迁移后的库不做删除用户/会话表的自动降级。回滚恢复变更前 auth 备份并回退网站版本，会使备份之后的新会话失效；不回滚业务库。

## 编译、创建初始管理员

在认证 Worktree 根目录运行：

```sh
export PATH="/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH"
pnpm install --frozen-lockfile
pnpm build:shared
node modules/auth/scripts/generate-ui.mjs
pnpm exec tsc -p modules/auth/tsconfig.json

export DATA_ROOT="$PWD/var/dev"
export IKUN_AUTH_DEV=1
export IKUN_AUTH_ORIGIN=http://127.0.0.1:3600
node modules/auth/dist/src/cli.js bootstrap --username your_admin_name
```

`bootstrap` 必须在本机交互终端执行，隐藏输入并确认两次；不接受密码参数、环境变量或管道。只在没有超级管理员时创建，无默认密码，不输出密码。独立迁移命令为 `node modules/auth/dist/src/cli.js migrate`。生产取消 `IKUN_AUTH_DEV`，设置 HTTPS Origin 并保留相同 scope；开发 Cookie 仅允许 loopback HTTP。

## API

除登录和退出的特定处理外都需有效 session。所有写入须同源 JSON，已登录写入须 `X-CSRF-Token`。后台调用不得用客户端角色 Header 替代认证。

| 方法 / 路径 | 权限 | 内容 |
|---|---|---|
| POST `/api/v1/auth/login` | 匿名 + 限流 | username、password → Cookie、会话 DTO |
| POST `/api/v1/auth/logout` | 当前会话 | 撤销；重复退出返回成功并清 Cookie |
| GET `/api/v1/auth/me` | 本人 | user_id、username、tenant_id、role、must_change_password、csrf_token |
| POST `/api/v1/auth/password` | 本人 | current_password、new_password；换 Cookie |
| GET `/api/v1/auth/users` | superadmin | 当前单站点账号列表，不含 hash |
| POST `/api/v1/auth/users` | superadmin | username、password、role；201 + ETag |
| PATCH `/api/v1/auth/users/{id}` | superadmin | enabled；If-Match、Idempotency-Key |
| POST `/api/v1/auth/users/{id}/reset-password` | superadmin | password；If-Match、Idempotency-Key |

用户管理写入都需要 UUID Idempotency-Key；冲突返回 409。未登录 401、无权限 403、缺 If-Match 428、错误版本 409、限流 429 + Retry-After，错误含稳定 code/retryable/request_id。登录、退出、本人改密属于会话轮换协议，不持久缓存原始 token，因此不套账号管理幂等回放；退出本身幂等。

只读兼容适配 `GET /api/auth/session` 为跟踪候选返回 `{user:{id,username,role,must_change_password},csrf_token}`（带 request-id/no-store），其他旧认证路径不开放；是否保留由总管评审。UI 页面为 `/login`、`/auth`、`/auth/users`、`/auth/password`。

## 验证和隔离 Next 预览

```sh
node --test modules/auth/tests/*.test.mjs
node --check modules/auth/static/auth.js

# 在 ignored test-results 中复制当前基础源码和本模块候选，不修改 apps/website。
node modules/auth/scripts/prepare-preview.mjs
NEXT_TELEMETRY_DISABLED=1 pnpm --dir modules/auth/test-results/next-preview --filter @ikun/website build

# 可选浏览器测试驱动，Python 只用于测试，不是网站运行依赖。
python3.11 -m venv modules/auth/.venv
modules/auth/.venv/bin/python -m pip install -r modules/auth/requirements-browser.txt
modules/auth/.venv/bin/python -m playwright install chromium
IKUN_NODE="$(command -v node)" modules/auth/.venv/bin/python modules/auth/tests/browser_smoke.py
```

已有 Chromium 可通过 `IKUN_TEST_CHROMIUM` 指定。浏览器测试使用临时本地端口和临时 auth.db；验证生产 Next 构建的首页拦截、登录、账号管理、首次改密、只读拒绝、退出，以及 1440px/390px 布局。截图与 JSON 结果在 `test-results/`，进程和临时 DB 自动清理。

正式主站路由、项目/Hunter/Tracking BFF 读取清单、现有 SSE 消费者、TLS/Cloudflare、公网认证与业务功能仍由总管集成验收；模块证据不能代表这些路径已上线。接入审阅差异详见 `HANDOFF.md`。
