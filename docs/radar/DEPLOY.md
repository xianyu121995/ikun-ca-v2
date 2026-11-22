# 模式雷达：网站入口已取消

ikun 已取消 flap+four 在 ikun.ca 上的监控展示。这次代码变更只去掉网站表面，不安装、不停止、不删除生产上的 mode-radar。

已经从网站去掉的内容：

- 侧栏「flap+four监控」（显示在「猎手项目追踪」旁边）
- `/radar`、`/prototypes/radar`
- `/api/v1/radar/snapshot`、`/api/v1/radar/events`
- 登录后全站的模式雷达角标、toast，以及连到本机桥的 SSE 客户端
- 网站进程读取 `IKUN_RADAR_ORIGIN` / `IKUN_RADAR_TOKEN`（历史上默认 `http://127.0.0.1:3921`）

猎手监控、猎手项目追踪和站点其余页面保持原样。不要把 `IKUN_RADAR_*` 加回网站环境，不要为了雷达切换 `/opt/ikun/current`，不要重启 hunter。

## 仍留在机器上的服务端钩子

`services/mode-radar` 还在仓库里。如果生产已经按 unit 跑起来，进程会继续写自己的库，并在 token 足够长时监听本机只读桥：

| 钩子 | 位置 | 说明 |
|---|---|---|
| systemd 单元 | `mode-radar.service`（模板在 `services/mode-radar/deploy/mode-radar.service`） | `ExecStart` 使用 `/var/lib/mode-radar/radar.sqlite3` |
| 数据目录 | `/var/lib/mode-radar` | 只属于雷达。保留，不要删除，不要迁走 |
| 数据库 | `/var/lib/mode-radar/radar.sqlite3` | 保留。这次变更没有任何清理或迁移代码 |
| 环境文件 | `/etc/mode-radar.env`（示例不含真实值） | 保留，权限维持 `0600` |
| 本机桥 | `127.0.0.1:3921` 的 `/health`、`/v1/snapshot`、`/v1/events` | 网站已不再连接。桥只在 mode-radar 进程还活着时存在 |
| 外部通知 | webhook / Telegram，默认关闭 | 不在这次变更里打开 |

代码副本如果已单独放在 `/opt/mode-radar`，那是服务自己的目录，不是 `/opt/ikun/current`。不要用这次网站发布去覆盖或切换 current。

## 稍后的生产步骤（本 PR 不执行）

等单独批准后再在雷达所在机器上做。不要 SSH 进生产当作这次合并的一部分。

1. `systemctl stop mode-radar`
2. `systemctl disable mode-radar`
3. 确认没有残留的 `radar.main` 进程仍在监听 `127.0.0.1:3921`
4. 保留 `/var/lib/mode-radar`、`radar.sqlite3` 和 `/etc/mode-radar.env`
5. 不要删除数据库，不要清空 StateDirectory
6. 不要重启 hunter，不要改 Watch、ALPHA、`hunters.enabled` 或 sniper/wallet 路径
7. 不要切换或重启 `/opt/ikun/current` 上的网站以外的服务；网站发布按网站自己的流程走，不带雷达页面

停掉服务之后，网站不会再显示雷达，因为页面和客户端已经不在。环境文件里如果还留着以前写给网站的 `IKUN_RADAR_ORIGIN` / `IKUN_RADAR_TOKEN`，可以留着，网站代码不再读取它们。不要为了清理这些变量去改 hunter 配置。
