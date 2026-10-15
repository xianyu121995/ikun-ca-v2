# Tracking storage authority · B3 v4

唯一物理库 `DATA_ROOT/tracking/tracking.db`，拒绝软/硬链接、非普通sidecar、外库身份及其他文件名。WAL/SHM用一次lstat检查，正常并发移除不构成外库；主库缺失不会由runtime重建。服务不打开hunter.db/projects.db/auth.db；测试通过固定owner API/CLI创建私有夹具。

本目录为SQL唯一权威。001固定B0原文/application_id=0x494b0202/owner=tracking；002无本地人类会话；003稳定sub_ID/commands/inbox/events/outbox。001—003字节保持原交付不变。002_legacy_reference仅校验旧v2 checksum，不在新库执行。004由夜间批准协议579a57f2e3e470525eb53f9f1f85ba75d25f3728授权，增加类型证据、固定expires_at、全局最小tweet账本、语义版本/私有签名键、短期ID快照及retention job，不增其他库/服务/方向凭据。

仅显式init/migrate升级；v3先成功验证备份再事务升级004，启动/HTTP/ready无DDL。沿用三/四列_schema_migrations及独立checksums，future/hash/name/必要结构拒绝；失败回滚；已v4仅验证。旧代码不接受v4，不自动降级。旧ID/seq/commands/审计/receipts保持，缺类型证据迁为unknown，在新feed隐藏而非猜原创。物理过期删除必须先有已核备份。

| 表 | 数据 |
|---|---|
| projects | canonical/sub_ID/X ID、人工确认、真实desired/remote/claim/revision/generation与恢复 |
| tweets / tweets_legacy | 分代观察和正文；各副本均15天，旧activity_id/seq不改写 |
| tweet_ledger | 永久最小tweet_id/first_seq/固定expiry/state；过期去掉首次接收与原sub引用，无正文/notes/raw |
| commands / public_receipts / receipts / audit | 持久命令、幂等、核验与审计，不由正文TTL清掉 |
| changes / tracking_outbox | 有效事件与待核观察；过期正文从SSE/outbox清除，保留event/hash/必要回执状态，不伪造accepted |
| feed_meta | 原子单调保留水位、持久clock_anomaly、语义版本、私有HMAC密钥、snapshot epoch、物理路径及ready栅栏 |
| feed_bases / feed_snapshots | 最多8个/60秒/64MiB的ID及非权威评分查询缓存，不是业务评分库，无正文副本 |
| retention_jobs | scheduled/backing_up/verified/deleting/completed及失败/退避，单次删除≤1000 ID |
| runtime | 单worker租约、进程心跳及WSS状态，不证明真实来源已接通 |

15天为1296000000 UTC毫秒，边界now>=expiry即隐藏。retention_now用单条UPDATE MAX RETURNING，即使autocommit GET/SSE也不能倒退。Worker启动及每300秒检查；无verified备份、时钟异常、容量/磁盘问题均停止物理删除，但公开读仍隐藏过期正文。备份仅本namespace tracking/backups/JOB/tracking.db，0700/0600，SQLite backup+完整性/外键/schema/ledger水位/SHA256/fsync；成功备份最多2份/24小时/合计1GiB。

恢复只写不存在的新路径。目标第一次身份提交与ready=0同事务；复制期间旧物理路径也拒绝启动。独立当前库或较新已验证备份提供非回退ledger horizon，不能以恢复包自身为源；源worker须停止，旧控制状态/未决命令/人工备注比当前落后则拒绝旧包并要求刷新备份。合并账本、清理和最终验证后才ready=1；中断目标不能开API。旧ID快照失效，旧SSE anchor清掉并返回422。不能证明水位时拒绝，不承诺任意丢盘零RPO。CLI和接线见本模块python/NIGHT-HANDOFF.md。

订阅移除需实际远端absent且命令成功后排除，失败不假移除；停止历史仍受15天窗口。无跨库外键/ATTACH/级联，不改主页/猎手或旧共享Watch。
