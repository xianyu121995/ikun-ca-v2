# 模式雷达：隔离部署清单（先不执行）

这是给后续运维看的准备说明。本文件不授权在生产机上安装、重启或发布。当前网站服务器 `13.193.157.88` 上没有 mode-radar 进程或数据。附件 README 里的 `root@YOUR_SERVER` 和 `install.sh` 只是上游模板，不能拿来当这次的生产操作。

这次交付只包含代码、测试和下面的 unit 模板。不要合并，不要部署，不要让网站去连真实节点。

## 要新增的东西

只增加一个独立进程，不改猎手、追踪、项目管理、Cloudflare 隧道、443 上的 xray，也不碰 8443。

| 组件 | 位置 | 作用 |
|---|---|---|
| `mode-radar` | 新用户、新目录、新 sqlite | 文档/仓库限速检查；有 WSS 时订阅 `newHeads` 和 `logs` |
| 本机桥接 | `127.0.0.1:3921` | 只读 `/health`、`/v1/snapshot`、`/v1/events`。需要至少 32 位 token |
| 网站读取 | 现有 Next `127.0.0.1:4000` | 登录后的 `/radar` 和 `/api/v1/radar/*`。浏览器不直连 3921 |

网站前面没有 nginx/caddy。不要把附件里的 `/monitor` 静态目录挂到公网。10 分钟一次的静态导出也不能当作站内通知。通知是网站会话后面的 SSE：新连接不回放历史，断线用 `Last-Event-ID` 去重。

建议路径：

- 代码：`/opt/mode-radar`（只放 `services/mode-radar` 里的 `radar/` 与配置）
- 状态：`/var/lib/mode-radar/radar.sqlite3`
- 环境：`/etc/mode-radar.env`，权限 `0600`
- unit 模板：`services/mode-radar/deploy/mode-radar.service`

网站侧只增加两个环境变量，并且要等单独批准的网站发布，不要为了这个去切 `current` 或重启 hunter / tracking / projects：

```bash
IKUN_RADAR_ORIGIN=http://127.0.0.1:3921
IKUN_RADAR_TOKEN=<与 RADAR_BRIDGE_TOKEN 相同>
```

## 还要用户决定的事

1. 雷达跑在哪一台机器。可以是网站同一台，但必须是新进程和新数据目录。现在这台网站机上没有可接入的现成数据。
2. BSC 的 `wss://` 地址。优先用已经在用的节点。不知道就留空，页面显示「未配置」。不要猜，不要写进源码，不要用 `http://` 轮询顶上，不要填 `127.0.0.1:8545`。
3. 桥接 token 由谁生成、放在哪一份 `0600` 环境文件里。
4. 什么时候把上面两个网站变量放进下一次网站专用 release。生产 Web 继续跑网站专用发布，不要改 hunter 的 `917b30a`，也不要动 DeepSeek 配置。

## 覆盖边界（页面上也会写）

- FLAP 文档、以及配置了 WSS 之后的 FLAP 合约身份和事件订阅，才是这条链上的实际范围。地址来自附件，不是本仓库重新核对过的官方全集。
- four.meme 有文档和两个社区仓库。名为 `fourmeme` 的链是空的，保持禁用。没有事件签名，就不能说链上事件已经覆盖。
- 文档和 GitHub 可以定时检查。链上不行。

## 回滚

只动这个新服务：

```bash
systemctl disable --now mode-radar
```

然后从网站环境里去掉 `IKUN_RADAR_ORIGIN` 和 `IKUN_RADAR_TOKEN`。页面会显示未配置，登录和其它业务不受影响。

`/var/lib/mode-radar` 只属于雷达。删掉它会丢掉雷达自己的基线，不会碰到 auth、projects、hunter、tracking 的库，也不会改 Watch、`hunters.enabled` 或共享监控名单。

代码回滚就是不合并这个 PR。不要用这份 unit 覆盖任何已有服务文件。
