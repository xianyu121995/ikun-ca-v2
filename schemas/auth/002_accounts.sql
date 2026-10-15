-- Auth 002 authoritative SQL. Apply through the explicit auth CLI only.

CREATE TABLE auth_users (
 id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('superadmin','user')),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), version INTEGER NOT NULL,
 must_change_password INTEGER NOT NULL CHECK(must_change_password IN (0,1)),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
) STRICT;
CREATE TABLE auth_sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(id),
 csrf_token TEXT NOT NULL, version INTEGER NOT NULL,
 created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL, expires_at INTEGER NOT NULL
) STRICT;
CREATE INDEX auth_session_user ON auth_sessions(user_id);
CREATE TABLE auth_login_limits (key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires_at INTEGER NOT NULL) STRICT;
CREATE TABLE auth_audit (id INTEGER PRIMARY KEY, actor_id TEXT, target_id TEXT, action TEXT NOT NULL, at INTEGER NOT NULL) STRICT;
CREATE TABLE auth_idempotency (
 actor_id TEXT NOT NULL, route TEXT NOT NULL, key TEXT NOT NULL,
 body_hash TEXT NOT NULL, response TEXT NOT NULL, expires_at INTEGER NOT NULL,
 PRIMARY KEY(actor_id,route,key)
) STRICT;
CREATE TABLE auth_migration_checksums (version INTEGER PRIMARY KEY, checksum TEXT NOT NULL) STRICT;
CREATE TABLE auth_site_scope (singleton INTEGER PRIMARY KEY CHECK(singleton=1), tenant_id TEXT NOT NULL) STRICT;
CREATE TABLE auth_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
