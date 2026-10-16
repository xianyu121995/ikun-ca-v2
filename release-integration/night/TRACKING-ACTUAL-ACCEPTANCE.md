# Tracking 真实迁入验收

2026-10-16T21:22:59.558256+08:00 完成，候选`2cf01fc3d90c346b8479a4dc97630232a31152b1`，固定原307d reader。

- 原完整树25225/25229/25230退出，停窗副本确认 **heartbeat=0 / disconnected / pong=NULL**；未SQL强清，未以过期心跳代替归零。
- 原输入三包加三证书的原CLI单事务新增 **1账号**；推文/账本/通知 **0/0/0**。同包replay全部新增0，全表指纹不变。正式canonical来自实际Projects，真实新subscription UUID未复用演练。原行/人工字段和四库inode保持，schema仍4。
- 在线/停窗/迁入后 **12份备份** 完整性/FK通过。固定307d在launchd **PID83544** 恢复，ready200、外采false；停服意图至恢复核验 5.172s。
- 网站54011完整树/IPC、Hunter78559/F9、Alpha9034、旧PG/监督进程/两个Tunnel、原配置/main/域名保持。本轮外部API/Watch写/Next构建/数据库覆盖 **0**。

实际receipt SHA `20017c8c3960b9901ea16852881d24c9f2afcfbe77ccfd04b78f4b6c5c9e667b`。14项本地运维夹具、3项原wrapper隔离验证和原CLI三证书副本验证通过，不重复相加。

三域迁入完成：Projects33、Hunter90、Tracking1；Auth未迁入。真实0x2a setup、临时样本采集、声音和24小时稳定验收尚未执行，不能据此宣称整体上线通过。
