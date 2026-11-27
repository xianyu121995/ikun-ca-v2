# 生产部署清单

这份清单只说明要新增什么。不要在合并前执行，不要重启无关服务。

服务器：东京 `ikun-server`（13.193.157.88）。代码进入已批准的 `/opt/ikun/current` 之后再做下面的事。

## 新增

1. 系统用户 `hackathon`，不要复用 `ikun` 或 `ubuntu` 的家目录密钥。
2. 数据目录 `/var/lib/ikun-hackathon`，属主 `hackathon`。
   - `hackathon.sqlite3` 保持 `0600`，网站用户不能读。
   - `snapshot.json` 由进程写成 `0644`。目录需要 `0755`，这样网站用户只读得到快照。
3. `/etc/ikun-hackathon.env`，权限 `0600`，内容见 `hackathon.env.example`。这里没有第三方密钥。
4. 安装 `ikun-hackathon.service`。`User=hackathon`（不要改成 DynamicUser，网站进程要能读快照）。`Restart=always`，没有结束日期。默认大约每 15 分钟核对一轮；已完整结束的赛事会放慢，读取失败的来源继续重试。已知但不在目录里的官方页面写在 `config.json` 的 `manual_sources`，不要只靠临时命令。然后：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ikun-hackathon.service
```

只操作 `ikun-hackathon.service`。

## 网站要改的唯一配置

给 `ikun-web.service` 增加一个 drop-in，不要改 Hunter、Tracking、Projects、Tunnel、backup、health 的 unit：

```
[Service]
Environment=IKUN_HACKATHON_SNAPSHOT=/var/lib/ikun-hackathon/snapshot.json
```

网站用户只需要这条路径的读权限。改完后只重启 `ikun-web.service`，让它读到新页面和新的环境变量。

路由：`/hackathons`。

## 不要做

- 不要合并到 `ikun/live` 之外的发布动作代替这份清单；清单本身也不是批准。
- 不要重启 `ikun-hunter`、`ikun-tracking-live`、`ikun-projects`、`ikun-tunnel`、`ikun-backup`、`ikun-health`。
- 不要改 Cloudflare Tunnel、旧服务、生产数据库或域名。
- 不要把 sqlite、WAL、cookie 或 `.env` 放进 Git。
