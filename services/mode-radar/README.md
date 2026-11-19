# mode-radar 0.2.0-ikun

隔离的 FLAP / four.meme 模式雷达。这一版是对用户附件 `mode-radar 0.1.0` 的审查改写，不是把附件里的安装说明当成已经授权的生产操作。

它只观察公开文档、GitHub 文件树，以及在配置了 `wss://` 之后的 `newHeads` / `logs` 订阅。它不交易、不签名、不调用付费接口，也不读取猎手、追踪或 Watch 的库。

## 和 0.1.0 的差别

- 链上不再使用 HTTP `eth_getLogs` 轮询。公共 RPC 已从默认配置移除。
- 没有 `RADAR_WSS_BSC` 时，BSC 链上路径是「未配置」，进程不会改用 HTTP。
- 明确拒绝 `127.0.0.1:8545` 和 `wss://127.0.0.1:8545`。那是钱包/sniper 专用端口。
- 第一次运行只把配置里的已知取值记成基线，不把它们报成新变化。
- 文档和仓库仍是限速定时检查。页面或文件消失会记成删除。抓取失败不会把整个目录当成被删光。
- four.meme 的事件枚举仍然未配置。名为 `fourmeme` 的链是空的，保持禁用。BSC 合约表里的 TokenManager 只做身份比对，不代表事件已覆盖。
- 新公开仓库只在已核实的 GitHub owner 下发现。当前只有官方文档写明的 `flap-sh`。`four-meme-community` 仍只做原来的文件树对比，不把它的新仓库当成官方。证据见 `docs/radar/GITHUB-OWNERS.md`。发现周期默认 1 小时，不读仓库内容。
- 网站通知走本机回环上的只读 HTTP + SSE，不走未认证的公网 webhook。10 分钟静态导出不能当作及时通知。

## 命令

```bash
python3 -m radar.main --once
python3 -m radar.main --loop
python3 -m radar.main --doctor
python3 -m radar.main --events 20
python3 -m radar.main --state
python3 -m unittest discover -s tests
```

`--loop` 在 `RADAR_BRIDGE_TOKEN` 足够长时，才会在 `127.0.0.1:3921` 提供 `/health`、`/v1/snapshot` 和 `/v1/events`。新连接不回放历史；`Last-Event-ID` 只补这个游标之后的事件。

## 不要做的事

不要执行任何会安装 systemd、创建用户或重启现有网站/猎手/追踪/隧道的脚本。部署步骤写在 `docs/radar/DEPLOY.md`，等明确批准后再由运维执行。
