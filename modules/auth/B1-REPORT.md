# B1 最终需求修订交付 · 2026-10-15

本地认证候选按用户最后确认的 B1 开发指令修订。原 `48d9dd4d5f955f9e1db7709e5c66c65826fb5ab0` 方案由本次新提交替代，旧报告原文保存在 `B1-REPORT-48d9dd4.md`，原失败历史仍在 `FREEZE.md`。**不得将原59项/旧Python候选结果算入本次验收。**

原独立 Worktree `ikun-ca-v2-worktrees/auth` / `codex/auth`；基线48d9dd4，固定B0 `85be3bd6dce25d82033b6cb1a7157aaa39bd571e`，公共UI `486294ac3255b08fdb13a307ee15f96c571020d9`。最新用户需求替代此前 phase2-v1.0.0 的网页账号管理和本人改密协议；共享契约文件未擅改，必须同步的收件差异列在 `INTEGRATION.md`。

## 最终实现

| 最终需求 | 实现和证据 |
|---|---|
| Next.js + TypeScript / 不新增服务 | 复用认证核心，React App Router 专属路由放在本模块 integration 候选；真实生产 Next build + next start 验收。Python仅浏览器驱动 |
| 独立auth.db | 只打开DATA_ROOT/auth/auth.db；schema002/checksum和旧记录保留。没有修改任何业务DB、worker、监控引擎、共享包或锁文件 |
| 两种角色 | superadmin/user；user只有经审阅的业务只读清单和本人密码；伪造身份头/跨scope均拒绝 |
| 只有一个管理员 | CLI create只能user，不接受角色参数；bootstrap在事务内防重复，包括并发初始化。保留角色列无单管理员UNIQUE，最后有效管理员禁止禁用 |
| 纯本地账号管理 | bootstrap/create/disable/enable/reset-password/recover-admin/list，真实PTY验收全部七项；密码隐藏双输，拒绝参数/环境变量/管道密码；本地恢复不需要旧密码或网页会话 |
| 没有网页账号管理 | 删除旧HTML/CSS/JS及用户管理处理器、分页/管理领域入口；旧users页面/API对所有身份404，can_manage_users恒false。没有注册、删除、改角色API |
| 首次强制改密 | 包括初始超级管理员，创建/重置/恢复均置must_change_password；业务页面/API/Server Action服务端禁止，改URL/直接API不可绕过 |
| 主动改密 | 验证原密码；事务内更新hash/version、撤销全部旧会话、创建唯一新token；新Cookie给当前浏览器，旧设备立即401。插入新会话失败时整个事务回滚有专测 |
| 7天会话 | 默认604800秒绝对期限，不因访问续期；配置上限及认证按session_created_at强制7天。第7天前1秒/正好第7天、持续访问、重启及配置超限自动测试；真实Next临时DB还验证7天存储期限与模拟过期 |
| 安全 | 保留原Argon2id 64MiB/3次、最多4个异步hash，安全Cookie、CSRF/Host/Origin、持久限流、安全错误、DB0700/0600、token摘要、SSE撤销；没有真实凭据 |
| 实际入口鉴权 | 统一getSession/requireIdentity/requireSuperadmin/withAuth；Next页面requireAuthPage和requireSuperadminAction。真实Route Handler及Server Action在Proxy排除路径独立验证匿名/reader/强制改密/CSRF，不能靠隐藏按钮或Proxy放行 |
| 公共UI | 实际登录LoginPanel、改密Input/Button/Panel、Alert、AppShell、Skeleton加载与pending。1440×1000及390×844；侧栏只有3业务入口，右上用户菜单仅用户名/本人改密/退出，无账号管理 |

## 自动化结果

**新版 Node 测试54/54通过，失败/跳过/取消均0，约50.2秒。** 新版保留原迁移/安全/SSE保障的适用测试，网页管理/分页/管理API测试由“始终不可用”与本地CLI方案替代，不能把测试数量变化解释为旧59项完整保留。

覆盖匿名、reader多种写入、管理员、强制改密、7天边界、禁用/启用/重置/恢复、全设备撤销、本人改密安全建立新会话、原子回滚、并发bootstrap/reset、最后管理员、CSRF、限流重启、弱密码/请求上限、生产Cookie、路径物理隔离、SSE静默和发块前撤销、旧schema兼容/失败回滚/只读readiness等。

严格TypeScript编译和固定B0/公共UI的隔离串行生产构建通过；离线 frozen 安装使用本模块私有cache，不改根锁和其他Worktree依赖。最终输入hash与浏览器结果保存在本地ignored回执，提交后绑定完整Git SHA。

## Chromium 验收

使用本机 Chromium 内核 Chrome 的 Playwright 驱动，真实 next start。七项CLI均为真实PTY；浏览器串联登录、初始管理员/普通用户首次改密、管理员本地恢复、普通用户禁用/启用/重置、主动退出及过期。

- 真实业务边界夹具：匿名API401；user写403、只读成功；强制改密API403/页面重定向；管理员写成功。
- Proxy排除路径：实际Route Handler自行鉴权；实际Server Action对admin成功，对user/强制改密/伪CSRF拒绝。
- 本人改密后新Cookie可用，旧Cookie立即401；禁用/恢复/重置同样撤销；启用不复活旧Cookie。
- 生产组件原生密码表单共4组：登录/改密 × JS禁用/JS chunks阻断，均为固定同源POST并415拒绝；虚构密码未进入URL、浏览历史、响应和Next日志。
- 1440×1000和390×844截图；手机无横向溢出；page errors为空。
- DATA_ROOT实测只有auth，业务库数量0；HTTP readiness三次不改schema元数据；测试finally停止自己的Next进程并清理临时DB。

本地ignored证据：`test-results/b1-final-v2-regression.log`、`b1-build.json/log`、`b1-preview.json`、`b1-final-v2-browser.json`、`b1-final-browser-*/`与`b1-final-v2-receipt.json`提交后SHA回执。屏幕截图只含虚构测试账号。

## 实际修复/失败记录

本轮首次Next构建发现测试夹具相对导入少一级，修正后完整重建通过；首次Chromium运行被沙箱禁止绑定本地端口，改为授权本地执行。随后公共Input标签含必填星号导致测试精确label定位超时，改用稳定的name定位后完整验收通过，没有为通过测试修改公共UI。早期目录/Next日志保留，不把失败计作成功。

## 复验命令

```sh
pnpm exec tsc -p modules/auth/tsconfig.json
node modules/auth/scripts/prepare-preview.mjs
node modules/auth/scripts/build-preview.mjs
node --test --test-concurrency=1 modules/auth/tests/*.test.mjs
IKUN_NODE="$(command -v node)" IKUN_TEST_CHROMIUM="/path/to/chromium" \
  modules/auth/.venv/bin/python modules/auth/tests/browser_smoke.py
git diff --check
```

提交完成后运行 `node modules/auth/scripts/final-receipt.mjs`，验证Git/blob、构建、浏览器输入hash和干净工作区一致，并生成绑定完整SHA的本地回执。

使用既有Node24.22与独立依赖。CLI使用、生产HTTPS/Cookie配置见README；接口与接线示例见INTEGRATION。

## 交接限制

交付为**最终需求的本地B1认证模块与Next接线候选**，等待总管审查具体新SHA后协调主站接入。`integration/preview-only/**`全部是隔离验收夹具，不可整包部署；proxy/readiness/依赖/共享DTO须由总管收件审阅。没有执行真实Projects/Hunter/Tracking业务集成、跨进程可信IPC、公网Cloudflare/TLS、生产账户或生产负载验收，不能冒充C0/D0。

没有merge/rebase/reset/amend/push或部署；不新增驻留服务，不访问生产或业务数据。新提交仅modules/auth/**。原冻结历史不改写。
