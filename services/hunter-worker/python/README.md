# B4 正式v2候选入口

本批研究PATCH、七天清理、迁移/恢复、鉴权及独立后台运行的权威说明为 [integration/README-B4.md](integration/README-B4.md)，验收为 [../B4-REPORT.md](../B4-REPORT.md)。生产候选经Node24 compiled入口 execve Python，显式HUNTER_ENGINE=python/v2_mode及私有DATA_ROOT，外采关闭；不使用Worktree、旧服务DB/端口、cwd .env或本地免密回退。下文保留的是早期私有候选/夹具历史，不作为正式API或部署命令。

# HunterRadar 独立候选

已有实现和真实验证、启动方式、权限/契约差异、未验证项均见上级 [FREEZE.md](../FREEZE.md)。本目录只是 Hunter 模块候选，未部署、未完成正式网站/项目模块联调。

代码：`hunterradar/`；SQL：`hunterradar/schema.sql`；独立测试：`tests/`；证据：`docs/`；网站接入候选：`integration/`。只允许自己的 hunter.db。

当前来源协议依据：

- [6551 官方 WSS 协议](https://github.com/6551Team/opentwitter-mcp)；以外层监控账号到 content 目标为方向，并验证 JSON 字符串 content。
- [TwitterAPI.io 官方 Following 文档](https://docs.twitterapi.io/api-reference/endpoint/get_user_followings)：最新关注在第一页、pageSize=20、最少预留60 credits/请求。额度账本是本模块的保守预留，不代表供应商实际余额或已对账费用。

项目资料是 hunter.db 内的人工候选研究数据；不代替 projects 主数据。服务 API、Next BFF/iframe 与 v2 EventEnvelope 都须按冻结说明由总管评审后集成。
