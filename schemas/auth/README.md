# auth.db 迁移归属

登录系统窗口，唯一物理路径 `DATA_ROOT/auth/auth.db`，application_id `0x494b0204`。保留 foundation1，业务版本2。

- `002_accounts.sql` 为唯一正式 SQL 权威。`modules/auth/scripts/generate-schema.mjs` 生成 `src/schema.ts`，并绑定 B0 `85be3bd6` 的 foundation 定义与校验和。
- 只通过显式 CLI migrate/bootstrap 应用。公共 `_migration_checksums(version,sha256)` 为新 registry；任何 HTTP/只读 readiness 不迁移。全部 INSERT 显式列名。
- `002_accounts.legacy.sql` 为冻结 `aa3cf65` 的兼容证据，不是第二个迁移器。已应用旧 Auth2 时，校验冻结 legacy hash、保留 `auth_migration_checksums` 全部记录、用户/会话/回执/原 metadata 行与可选 checksum 列，仅显式补入新 registry 和 cursor metadata。
- 新增 `auth_metadata` 保存分页 cursor HMAC key。角色仅 superadmin/user，scope 固定 ikun-main；不开放注册，不复制旧版账号。
- 错误 checksum、future version、外来标记、scope/结构错均拒绝；失败事务回滚并保留现场。测试覆盖新库、foundation升级、冻结Auth2升级、重启/重复迁移、失败回滚与备份恢复到新路径。

B0 默认 maximumVersion=1 保持不变。准入 Auth2 的补丁只在本模块隔离预览候选内显式配置，仍须本领域验证 checksum/scope。最终收件由总管审核。详见 `modules/auth/B1-REPORT.md`。
