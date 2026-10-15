# projects.db 迁移归属

由项目领域窗口持有。正式网站数据库未执行业务迁移。B2 的唯一迁移器是 `modules/projects/integration/ipc-entry.py --migrate`；只处理 `DATA_ROOT/projects/projects.db`。

隔离候选的迁移源位于 [001_projects.sql](../../modules/projects/candidate/projects_service/migrations/001_projects.sql) 与 [002_tenant_queries.sql](../../modules/projects/candidate/projects_service/migrations/002_tenant_queries.sql)。候选有自己的校验和 ledger，使用本库 application_id `0x494B0203`，可以在隔离测试中保留 foundation 的元数据表再应用业务表。

001：项目/租户/稳定 ID、来源映射、独立候选身份、会话、幂等回执和审计。002：租户查询索引。所有表、外键、事务只在 projects.db；禁止 ATTACH 或跨库操作。

`001_foundation.sql` 保留 B0 foundation 原始字节，SHA256 为 cb3878b56fb3ea66c2a21668e1720381ea39f7f240fc2f39fd13238534cf02ac；`002_projects.sql` 为 B2 业务权威 SQL。版本/名称、application_id、store identity、`_migration_checksums` 和具体表列均验明后运行；未知版本/校验和拒绝，health/API 不迁移。支持旧 foundation ledger 的额外 checksum 列，保留已存在的 foundation 行。

旧候选业务数据升级保留 ID、来源和审计，将旧表保存为 `legacy_*_v1`，不清库。旧候选若仍有人类凭证/会话，显式报 `LEGACY_IDENTITY_RETIREMENT_REQUIRED` 并保持原库；须先由 owner 审查身份退役流程，不能偷偷复制到正式业务表或删除历史。正式服务从不使用这些旧身份。

唯一业务 writer 是 Python 项目域。网站只通过私有 IPC 调用，Auth 用已验收 B1 组件。不能两个迁移器同时操作同一文件；恢复使用本库一致性备份，不提供破坏性 down，不迁移/删除其他业务库。
