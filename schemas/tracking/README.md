# Tracking storage authority · B3

唯一物理库 `DATA_ROOT/tracking/tracking.db`，拒绝软/硬链接、外库身份及其他文件名。服务不打开 hunter.db/projects.db/auth.db；测试通过固定owner API/CLI创建私有夹具。

本目录为SQL唯一权威。001保留固定B0三列STRICT ledger原文，application_id=0x494b0202、_store_identity=tracking。002_tracking为无本地人类会话的业务基线；003添加稳定订阅/命令inbox/事件/观察outbox。002_legacy_reference仅校验原候选v2 checksum，不在新库执行。

仅显式init/migrate事务升级；启动/HTTP/ready不DDL、不清库。沿用三/四列 `_schema_migrations(version,name,applied_at[,checksum])`，显式列INSERT；独立 `_migration_checksums(version,sha256)`。future/version/name/hash、缺表/列/必要唯一索引均拒绝。失败回滚；已是v3仅校验，不修补损坏结构。

旧v2保留ledger/receipts/推文/seq及tweets_legacy，为canonical项目补稳定sub_UUID。无法映射的旧ID/generation或非空sessions/login_limits停下待人工审查，不丢弃或搬到其他库。新库不创建、不使用人类会话表。

| 表 | 数据 |
|---|---|
| projects | canonical/sub_ID/X ID、人工确认、desired/remote/claim/revision/generation、baseline/重试/恢复窗口 |
| tweets | 最小动态、nullable occurred、received、source；唯一sub/generation/tweet_id |
| commands | command_id/hash/envelope/核验状态；远端写前持久remote_attempted |
| changes | 稳定evt_ID、脱敏SSE/replay seq |
| tracking_outbox | 观察envelope、pending/error/receipt；B2收件未实现，不假称投递 |
| runtime | 30秒租约、worker心跳、WSS ACK/pong |
| public_receipts / receipts | 新PATCH与旧幂等结果，不自动清理 |
| audit | 本模块审计，不含凭据或原始Hunter事件 |

订阅移除保留历史，不改主页。没有跨库外键/ATTACH/级联。备份用本库SQLite backup API，不复制运行中的单个DB/WAL；迁移前备份，旧代码回滚只用兼容库/独立恢复副本，不自动降级v3。
