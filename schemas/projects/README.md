# projects.db 迁移归属

由项目领域窗口持有。当前基础 schema 仍为版本 1，正式网站数据库未执行业务迁移。

隔离候选的迁移源位于 [001_projects.sql](../../modules/projects/candidate/projects_service/migrations/001_projects.sql) 与 [002_tenant_queries.sql](../../modules/projects/candidate/projects_service/migrations/002_tenant_queries.sql)。候选有自己的校验和 ledger，使用本库 application_id `0x494B0203`，可以在隔离测试中保留 foundation 的元数据表再应用业务表。

001：项目/租户/稳定 ID、来源映射、独立候选身份、会话、幂等回执和审计。002：租户查询索引。所有表、外键、事务只在 projects.db；禁止 ATTACH 或跨库操作。

正式迁移编号、唯一 writer、认证接线由总管集成时分配。候选凭证表不替代正式 auth.db；不能两个迁移器同时操作同一文件。恢复使用本库一致性备份，不提供破坏性 down，也不迁移/删除其他业务库。
