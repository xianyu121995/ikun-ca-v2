CREATE TABLE IF NOT EXISTS _schema_migrations (
 version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS _store_identity (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), store_name TEXT NOT NULL
);

                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY, name TEXT NOT NULL, handle TEXT NOT NULL UNIQUE,
                    notes TEXT NOT NULL DEFAULT '', confirmed_by TEXT NOT NULL, confirmed_at REAL NOT NULL,
                    desired TEXT NOT NULL CHECK(desired IN ('running','stopped','removed')),
                    remote_state TEXT NOT NULL DEFAULT 'unknown', observed_at REAL,
                    claim TEXT NOT NULL DEFAULT 'none', status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT, attempts INTEGER NOT NULL DEFAULT 0, next_retry REAL NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 1, generation INTEGER NOT NULL DEFAULT 1,
                    generation_at REAL NOT NULL, last_backfill REAL, coverage TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tweets (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(project_id),
                    handle TEXT NOT NULL, tweet_id TEXT NOT NULL, text TEXT NOT NULL, created_at REAL NOT NULL,
                    received_at REAL NOT NULL, source TEXT NOT NULL, generation INTEGER NOT NULL,
                    UNIQUE(handle,tweet_id)
                );
                CREATE INDEX IF NOT EXISTS tweets_project ON tweets(project_id,seq);
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY, project_id TEXT, actor TEXT NOT NULL, action TEXT NOT NULL,
                    at REAL NOT NULL, detail TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS receipts (
                    key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL, at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, role TEXT NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_limits (
                    identity TEXT PRIMARY KEY, window_at REAL NOT NULL, attempts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime (
                    id INTEGER PRIMARY KEY CHECK(id=1), worker_id TEXT, heartbeat REAL,
                    connection TEXT NOT NULL DEFAULT 'disconnected', pong_at REAL, error TEXT
                );
                INSERT OR IGNORE INTO runtime(id) VALUES(1);
                PRAGMA user_version=1;
