CREATE TABLE IF NOT EXISTS _store_identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1),store_name TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS _schema_migrations (version INTEGER PRIMARY KEY,name TEXT NOT NULL,applied_at TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS _hunter_migrations (version INTEGER PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS hunters (
 id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE, user_id TEXT UNIQUE,
 name TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1,
 deleted_at REAL, created_at REAL NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 generation INTEGER NOT NULL DEFAULT 1, followers INTEGER, mode TEXT,
 profile_status TEXT NOT NULL DEFAULT 'pending', next_profile_at REAL NOT NULL DEFAULT 0,
 active_since REAL NOT NULL DEFAULT 0,
 profile_failures INTEGER NOT NULL DEFAULT 0, profile_error TEXT,
 watch_covered INTEGER NOT NULL DEFAULT 0, baseline_ready INTEGER NOT NULL DEFAULT 0,
 next_poll_at REAL NOT NULL DEFAULT 0, last_poll_at REAL, poll_failures INTEGER NOT NULL DEFAULT 0,
 poll_error TEXT, poll_warning TEXT,
 CHECK(mode IS NULL OR mode IN ('WSS','REST'))
);
CREATE TABLE IF NOT EXISTS seen_targets (
 hunter_id TEXT NOT NULL REFERENCES hunters(id), generation INTEGER NOT NULL,
 target TEXT NOT NULL COLLATE NOCASE, user_id TEXT,
 PRIMARY KEY(hunter_id,generation,target)
);
CREATE TABLE IF NOT EXISTS follow_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT UNIQUE NOT NULL,
 hunter_id TEXT NOT NULL REFERENCES hunters(id), hunter_x_id TEXT NOT NULL,
 generation INTEGER NOT NULL, target TEXT NOT NULL COLLATE NOCASE, target_id TEXT,
 target_name TEXT NOT NULL, description TEXT NOT NULL,
 occurred_at REAL NOT NULL, received_at REAL NOT NULL, window_at REAL NOT NULL,
 source TEXT NOT NULL, time_basis TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS follow_window ON follow_events(window_at,target,hunter_x_id);
CREATE INDEX IF NOT EXISTS follow_pair ON follow_events(hunter_x_id,target,window_at);
CREATE TABLE IF NOT EXISTS discoveries (
 target TEXT PRIMARY KEY COLLATE NOCASE, first_discovered_at REAL NOT NULL,
 name TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '', rating TEXT NOT NULL DEFAULT '待定', version INTEGER NOT NULL DEFAULT 1
 ,category TEXT NOT NULL DEFAULT '其他', stage TEXT NOT NULL DEFAULT '未知', ignored INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS task_outbox (
 id TEXT PRIMARY KEY, target TEXT UNIQUE NOT NULL REFERENCES discoveries(target),
 idempotency_key TEXT UNIQUE NOT NULL, request_key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
 body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt_at REAL NOT NULL DEFAULT 0, last_error TEXT, receipt_id TEXT,
 confirmed_by TEXT NOT NULL, confirmed_at REAL NOT NULL, delivered_at REAL, project_id TEXT
);
CREATE TABLE IF NOT EXISTS quota (
 provider TEXT NOT NULL, window TEXT NOT NULL, reserved INTEGER NOT NULL,
 PRIMARY KEY(provider,window)
);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS worker_lease (id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, actor TEXT NOT NULL,
 action TEXT NOT NULL, subject TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
);
