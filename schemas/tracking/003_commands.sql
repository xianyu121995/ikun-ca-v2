ALTER TABLE projects ADD COLUMN subscription_id TEXT;
ALTER TABLE projects ADD COLUMN x_user_id TEXT;
ALTER TABLE projects ADD COLUMN active_command_id TEXT;
ALTER TABLE projects ADD COLUMN baseline_ready INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX subscriptions_identity ON projects(subscription_id);
CREATE UNIQUE INDEX subscriptions_platform_identity ON projects(x_user_id) WHERE x_user_id IS NOT NULL;
CREATE TABLE commands (
 command_id TEXT PRIMARY KEY, body_hash TEXT NOT NULL, envelope TEXT NOT NULL,
 project_id TEXT NOT NULL, subscription_id TEXT NOT NULL, revision INTEGER NOT NULL,
 state TEXT NOT NULL, error_code TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
 request_id TEXT NOT NULL, remote_attempted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE public_receipts (
 actor_id TEXT NOT NULL, route TEXT NOT NULL, key TEXT NOT NULL, body_hash TEXT NOT NULL,
 response TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(actor_id,route,key)
);
ALTER TABLE tweets RENAME TO tweets_legacy;
CREATE TABLE tweets (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, activity_id TEXT NOT NULL UNIQUE,
 project_id TEXT NOT NULL REFERENCES projects(project_id), subscription_id TEXT NOT NULL,
 handle TEXT NOT NULL, tweet_id TEXT NOT NULL, text TEXT NOT NULL,
 created_at REAL, received_at REAL NOT NULL, source TEXT NOT NULL,
 generation INTEGER NOT NULL, UNIQUE(subscription_id,generation,tweet_id)
);
CREATE INDEX tracking_activity_order ON tweets(received_at,seq);
CREATE INDEX tracking_activity_project ON tweets(project_id,seq);
CREATE TABLE changes (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
 event_type TEXT NOT NULL, data TEXT NOT NULL, received_at REAL NOT NULL
);
CREATE TABLE tracking_outbox (
 event_id TEXT PRIMARY KEY, envelope TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
 error_code TEXT, receipt TEXT, updated_at REAL NOT NULL
);
