# auth.db 迁移归属

由登录系统窗口持有。独立物理数据库，application_id `0x494b0204`；基础版本 1。

`002_accounts.sql` 是认证候选的结构审阅副本。实际通过 `modules/auth/dist/src/cli.js migrate` 或首次 `bootstrap` 显式应用；迁移器同事务写入版本、SHA-256 校验和、固定 site scope。不要直接对业务库执行 SQL，不在 Web 请求中执行迁移。

新增表：`auth_users`、`auth_sessions`、`auth_login_limits`、`auth_audit`、`auth_idempotency`、`auth_migration_checksums`、`auth_site_scope`。仅 superadmin/user 两种角色，不开放注册、不创建默认用户、不复制旧库。详见认证模块 README 与 HANDOFF。
