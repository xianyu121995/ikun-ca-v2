# C0-lite 本机操作单

运行位置为 `/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration`。部署程序会把实际 SHA、端口、release、Python 与数据路径写入 `.runtime/c0-lite/deployment.json`，认证助手从新目录 owner/environment 记录读取实际值，没有手填 release 占位符。

## 本人应用账户

在 Mac 终端（真实 TTY）执行，密码由本人本地隐藏输入，首次网页登录再改密：

```sh
/Users/lvlei/.local/bin/python3.11 '/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/scripts/c0_auth.py' list
/Users/lvlei/.local/bin/python3.11 '/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/scripts/c0_auth.py' bootstrap --username admin
```

`admin` 是可自选的普通用户名。只有 list 显示空库才 bootstrap；若已有本人超管，保留用户名，改用 `recover-admin --username <list显示的现有用户名>`。禁止第二超管、SQL 改角色或删除认证库。

## Cloudflare 顺序

1. 本机登录管理 ikun.ca 的 Cloudflare 账号；确认 `v2.ikun.ca` 未被其他资源占用。若占用且归属不明，停止变更。
2. Zero Trust → Access controls → Applications → Add application → Self-hosted。新应用 public hostname 精确 `v2.ikun.ca`，覆盖所有路径。新 Allow policy 仅 Include 本人完整邮箱，现有 IdP 或 One-time PIN；其余默认拒绝。不得 Everyone/域名通配/Bypass。把本人邮箱、team、AUD 填入新目录 `config/cloudflare.local.json`。此时尚不发布 DNS。
3. 使用已安装 cloudflared 的官方本机浏览器授权。证书与 tunnel credentials 只保存在新 config 目录，权限 0600；不覆盖原配置、不运行全局 service install。先通过 `cloudflared tunnel --help` 核对 `--origincert`、`--config` 的位置，再执行 login；若官方命令写入默认新证书，先确认默认目录原先不存在，并将本次证书移动到独立 config，不能移动既有证书。
4. 用本次证书创建**新** `ikun-ca-v2-c0-lite` Tunnel。把实际 UUID、credential 路径填入上述本地 JSON。新 `config/cloudflared.yml` 只列 `v2.ikun.ca` → 回执中的 `http://127.0.0.1:端口`，末尾 `http_status:404`。`originRequest.access` 必须启用 `required: true`，teamName 与 audTag 绑定新应用；配置 validation 通过才继续。
5. Access 精确邮箱策略就绪后，才为 `v2.ikun.ca` 新增 CNAME 到**新** UUID 的 `cfargotunnel.com`。任何修改 apex/www/wildcard 或既有 Tunnel 的提示都停止；不使用 overwrite 参数。
6. 新 LaunchAgent `ca.ikun.v2.c0lite.tunnel` 以已安装 cloudflared 加**显式本次 config**运行，KeepAlive/节流/私密日志。不要 `cloudflared service install`，不要改既有 LaunchAgent。
7. 私密浏览器检查首先进入 Access，未允许邮箱不能访问；本人授权后才进入应用登录，再验证本人改密、项目增改/完成/恢复、普通用户只读、API 与 SSE 撤销。Cookie/验证码/Token 不发聊天，不导出原始 HAR。

缺少登录、本人邮箱、team/AUD 或证书时，停在对应步骤；本机 loopback 服务可以运行，公网状态保持 BLOCKED。Cloudflare 控制包包含权威原始步骤，位于 `../c0-lite-control/docs/c0-lite/CLOUDFLARE-STEPS.md`。

## 新环境检查与回滚

```sh
launchctl print gui/$(id -u)/ca.ikun.v2.c0lite.web
/Users/lvlei/.local/bin/python3.11 '/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/scripts/verify_c0_deployment.py'
```

第二条会故障演练并重启**新** web job，再在线备份新 Auth/Projects 库。备份在新根目录 `backups/时间戳`，不会替换 live 数据。当前为测试站手动备份，不声明已有定时备份或日志轮换。

若新站异常，仅 bootout `gui/$(id -u)/ca.ikun.v2.c0lite.web`；有本次新 Tunnel 时仅停其新 label 并移除本次新 v2 路由。保留整个新目录和数据库供回查，旧站继续运行。不能用 broad pkill、全局 supervisor stop、覆盖旧库来回滚。未来代码升级保留旧 release，修改新 label 的 release 路径前先备份；跨 schema 回退需恢复到另一个新数据路径验收，不能盲目降级数据库。

官方依据：[Self-hosted Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)、[本地 Tunnel](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/)、[Access policy](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/common-policies/)。
