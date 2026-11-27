# 黑客松监控

长期运行的 BNB Chain / BSC 官方黑客松核对服务。Agent ID 黑客松和 BNB Bangkok 只是第一批种子来源，进程不会在它们结束后退出。新的官方活动会在后续轮次里自动出现，已结束的活动留在归档。

它只读公开页面和公开 JSON：

- `https://www.bnbchain.org/en/hackathons` 以及每个活动详情页
- `https://www.bnbchain.org/en/blog` 最近几页，加上配置里固定盯住的文章
- 币安公告目录（最新活动、最新公告）里标题写明黑客松的条目，以及固定盯住的公告

交易赛、Blockchain Week、加速器不会因为出现在币安活动流里就被当成黑客松。官方黑客松目录里标题没有写黑客松的条目，会单独标成相关活动。

投稿如果只存在于 Google 表单、Luma 或币安问卷，页面会说明没有公开名单。没有来源链接的项目不会写进快照。

## 命令

```bash
python3 -m hackathon.main --once
python3 -m hackathon.main --loop
python3 -m hackathon.main --doctor
python3 -m unittest discover -s tests
```

在 `services/hackathon-monitor` 目录执行。`--loop` 默认每 30 分钟一轮，失败由 systemd 拉起，不设结束日期。

数据库只属于这个服务。网站读的是另一份 `snapshot.json`，不打开这个 sqlite 文件。

生产安装步骤见 `deploy/DEPLOY.md`。不要在未批准时安装 unit 或重启别的服务。
