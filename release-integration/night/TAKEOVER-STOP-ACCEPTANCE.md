# 获批旧侧停采与快照验收

状态 **PASS_APPROVED_OLD_SIDE_STOP_AND_SNAPSHOT_ONLY**。完成于 **2026-10-16 17:36:34（上海时间）**。执行候选 `3120e29c54ac2c2796a1fecad518d61cbe889461`，总管精确复审放行 `16f709836d18ae3e640ab76028bfa69eb6c45322`；原独立 Git 导出回归 **40/40**，不与此前30/35/39项累计。授权原文及历次修正见[操作收件说明](./TAKEOVER-OPERATOR-REVIEW.md)。

| 获批目标 | 实际结果 |
| --- | --- |
| ca.ikun.overload-tracking / 原 PID46545 | 禁用并 bootout，label 未加载，原进程退出；已有 disable_intent 对账复用，未重复禁用 |
| com.lvlei.ikun-auto-research / 原 PID38618 | 禁用并 bootout，label 未加载，原进程退出；plist 和现存文件保留 |
| 旧 Hunter / PID6466 | 复核 PID、启动时刻、cwd、父进程后一次 SIGTERM，原进程退出；没有强杀 |
| 父 login6465 | 未发送信号；最终复核时已不存在，不推断其退出原因 |

旧 disabled 解析器记录的 previousDisabled=None **不能证明原 override 键缺省**；原记录未改写。AI 的旧源目录/venv/入口在操作前已缺失，仅备份现存文件及缺失事实，不能承诺原样重启。

前置快照和最终快照各7份 SQLite，共 **14份**；全部独立重验 integrity/FK、表计数及封存元数据，DELETE journal、无 WAL/SHM。两批各有完整 PostgreSQL custom dump、TOC、解码 SQL 和导出事务快照内的100表计数；两次独立临时集群均实际恢复100表、计数一致，并已正常停止、无 postmaster.pid。260条 POLICY 的8个已批 NOLOGIN占位角色只在新集群创建，最低权限属性已检查；只证明数据恢复，**不证明生产权限语义复现**，原归档 owner/ACL 保留。

原始及最终备份合计 **66个资产引用哈希**递归复核通过；原7库和前置 dump 在修正后重验复用，没有覆盖原资产。三个历史失败（PG角色不足、临时恢复缺 POLICY 角色、本机 disabled 输出未识别）及原失败临时目录、日志全部保留。快照各有原始时间；各 SQLite 分别一致、PG事务内一致，**不是跨库分布式全局事务**。Alpha 和旧 PostgreSQL保持运行，后续导入必须由总管/owner按肯定自有范围过滤，完整备份不代表全量导入许可。

最终保护检查通过：Alpha9034、旧监督进程79489、旧PostgreSQL79494、旧Tunnel79502，以及 v2 web87924/Hunter2608/Tracking25225/Tunnel39523，均保持原身份。Alpha fresh/connected；v2三项 ready=200、两Worker外采仍关闭，原配置和四库物理身份保持。v2网站仍为 `0ce180c33ea4be350ac57daa7dbfa5b5221e58cb`，BUILD `X0CYNNjMlhJWNcjEpx1PF`，331源码/271构建哈希复验通过。没有重启v2、覆写四库、迁移schema、部署网站、改主域名/Cloudflare或合并main。

操作者直接平台请求、新WSS连接、Watch写均为0；没有远程Watch审计，不能把这个计数解释为对旧进程历史或远程状态的独立证明。当前磁盘代码审查也不能证明长期运行进程最初加载的字节。语音及原公网验收见[语音报告](./VOICE-HANDOFF.md)，本批没有重跑实际发声或真实来源链路。

实际运行命令为原Worktree中的已审入口：

```sh
python3 /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/scripts/with-heavy-lock.py --owner chief-review --timeout 600 -- /Users/lvlei/Documents/Codex/2026-10-11/codex-web3-workspace-codex-web3-next/outputs/web3-workspace/backend/.venv/bin/python release-integration/scripts/takeover_operator.py --execute --candidate 3120e29c54ac2c2796a1fecad518d61cbe889461
```

已退出0并释放共享锁。没有本轮自动审批拒绝。journal 为 `legacy_snapshots_ready_waiting_owner_imports`；迁移与真实联调未执行，等待总管收件后按owner门禁推进。恢复旧采集须重新核实唯一采集者、原启动策略和缺失AI入口；保留当前库，不自动回写备份或重启旧任务。本批没有执行回滚。

私密总回执：`.runtime/takeover-execution/IKUN-ONLY-2026-10-16/final-receipt.json`，SHA256 `9d6fac46e22cdd9587d16c2fe182c8d09f589890d8718be4824ec2a5e28d42ef`。独立停后保护回执 SHA256 `1e2e1accab6e2c291af41213e47852a040a5e6602887df8723901141fe0ef0a2`。数据、凭据、日志及原始备份均留本机私密目录，不入Git。完整来源、最终PG归档与计数文件哈希见[机器摘要](./takeover-stop-acceptance.json)。
