# Tracking schema ownership

仅 tracking-worker 打开 DATA_ROOT/tracking/tracking.db（本地路径可配置，文件名必须 tracking.db）。application_id 为 foundation 0x494b0202；沿用 _store_identity=tracking。

业务迁移来源：`services/tracking-worker/python/tracking/schema.sql`。启动/init 在自己的库执行事务迁移，在 `_schema_migrations` 记录版本 2、名称 tracking_new_tweet_v1、SHA-256 checksum。已有 foundation 版本 1 保留。checksum 不符拒绝启动，不自动覆盖或降级。测试覆盖 foundation→业务升级与身份/校验和拒绝。

| 表 | 数据 |
|---|---|
| projects | 项目 canonical ID 引用、人工确认、期望/远端状态、ownership reservation、revision、generation、重试与补采窗口 |
| tweets | NEW_TWEET 归一字段，handle+tweet_id 唯一，seq cursor，来源/接收时间 |
| runtime | 单 worker 30 秒租约、进程心跳、WSS ACK/pong 状态 |
| receipts | 按 principal/route 作用域持久幂等结果，无自动清理 |
| audit | 本模块管理操作，不含 secrets/原始猎手事件 |
| sessions / login_limits | 仅 standalone 调试页面的 session hash/限流；主站模式不允许本地登录 |

不建立跨库外键，不读写 hunter.db/projects.db/auth.db；project_id 只从人工确认后的业务输入接收。正式迁移前由部署 owner 在线备份自己的 tracking.db，回滚代码须与迁移兼容；不拷贝运行中 DB/WAL、不删除业务表或历史。
