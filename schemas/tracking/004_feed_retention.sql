ALTER TABLE tweets ADD COLUMN tweet_kind TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE tweets ADD COLUMN author_verified INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tweets ADD COLUMN type_evidence_version TEXT NOT NULL DEFAULT 'legacy-unknown';
ALTER TABLE tweets ADD COLUMN expires_at_ms INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tracking_outbox ADD COLUMN original_hash TEXT;
ALTER TABLE tracking_outbox ADD COLUMN original_receipt_hash TEXT;
CREATE TABLE tweet_ledger (
 first_seq INTEGER PRIMARY KEY AUTOINCREMENT, tweet_id TEXT NOT NULL UNIQUE,
 expires_at_ms INTEGER NOT NULL, first_received_at_ms INTEGER,
 origin_subscription_id TEXT, state TEXT NOT NULL CHECK(state IN ('unknown','visible','expired'))
);
CREATE INDEX tweet_expiry ON tweets(expires_at_ms);
CREATE TABLE feed_meta (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), semantic_revision INTEGER NOT NULL DEFAULT 1,
 cursor_key BLOB NOT NULL, snapshot_epoch TEXT NOT NULL, database_path TEXT NOT NULL, last_retention_now_ms INTEGER NOT NULL DEFAULT 0,
 clock_anomaly INTEGER NOT NULL DEFAULT 0, recovery_ready INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE feed_bases (
 basis_id TEXT PRIMARY KEY, actor_hash TEXT NOT NULL, query_hash TEXT NOT NULL,
 query_json TEXT NOT NULL, semantic_revision INTEGER NOT NULL, snapshot_epoch TEXT NOT NULL,
 as_of_ms INTEGER NOT NULL, expires_at_ms INTEGER NOT NULL, prepared_until_ms INTEGER NOT NULL,
 candidate_ids TEXT NOT NULL, subscription_ids TEXT NOT NULL, project_ids TEXT NOT NULL
);
CREATE TABLE feed_snapshots (
 snapshot_id TEXT PRIMARY KEY, actor_hash TEXT NOT NULL, query_hash TEXT NOT NULL,
 semantic_revision INTEGER NOT NULL, snapshot_epoch TEXT NOT NULL, as_of_ms INTEGER NOT NULL,
 expires_at_ms INTEGER NOT NULL, catalog_version TEXT, ordered_ids TEXT NOT NULL,
 ratings_json TEXT NOT NULL, counts_json TEXT NOT NULL
);
CREATE TABLE retention_jobs (
 job_id TEXT PRIMARY KEY, state TEXT NOT NULL, created_at_ms INTEGER NOT NULL,
 updated_at_ms INTEGER NOT NULL, high_water INTEGER, backup_path TEXT, backup_sha256 TEXT,
 error TEXT, retry_at_ms INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
 deleted_count INTEGER NOT NULL DEFAULT 0
);
CREATE TRIGGER feed_project_insert AFTER INSERT ON projects BEGIN
 UPDATE feed_meta SET semantic_revision=semantic_revision+1 WHERE singleton=1;
END;
CREATE TRIGGER feed_project_change AFTER UPDATE ON projects
WHEN OLD.name!=NEW.name OR OLD.notes!=NEW.notes OR OLD.desired!=NEW.desired
 OR OLD.remote_state!=NEW.remote_state OR OLD.active_command_id IS NOT NEW.active_command_id BEGIN
 UPDATE feed_meta SET semantic_revision=semantic_revision+1 WHERE singleton=1;
END;
CREATE TRIGGER feed_removed_result AFTER UPDATE OF state ON commands
WHEN OLD.state!=NEW.state AND EXISTS(SELECT 1 FROM projects WHERE active_command_id=NEW.command_id AND desired='removed') BEGIN
 UPDATE feed_meta SET semantic_revision=semantic_revision+1 WHERE singleton=1;
END;
CREATE TRIGGER feed_tweet_change AFTER UPDATE ON tweets
WHEN OLD.text!=NEW.text OR OLD.created_at IS NOT NEW.created_at OR OLD.tweet_kind!=NEW.tweet_kind
 OR OLD.expires_at_ms!=NEW.expires_at_ms OR OLD.author_verified!=NEW.author_verified BEGIN
 UPDATE feed_meta SET semantic_revision=semantic_revision+1 WHERE singleton=1;
END;
CREATE TRIGGER feed_tweet_delete AFTER DELETE ON tweets BEGIN
 UPDATE feed_meta SET semantic_revision=semantic_revision+1 WHERE singleton=1;
END;
CREATE TRIGGER feed_generation_insert AFTER INSERT ON tweets
WHEN EXISTS(SELECT 1 FROM tweets WHERE subscription_id=NEW.subscription_id AND tweet_id=NEW.tweet_id AND seq!=NEW.seq) BEGIN
 UPDATE feed_meta SET semantic_revision=semantic_revision+1 WHERE singleton=1;
END;
