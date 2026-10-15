ALTER TABLE discoveries ADD COLUMN first_discovered_at_us INTEGER;
ALTER TABLE discoveries ADD COLUMN profile_json TEXT;
ALTER TABLE public_changes ADD COLUMN initial_publication INTEGER NOT NULL DEFAULT 0 CHECK(initial_publication IN (0,1));
CREATE TABLE target_discovery_ledger (
 scope TEXT NOT NULL CHECK(scope='ikun-main'), platform TEXT NOT NULL CHECK(platform='x'),
 x_user_id TEXT NOT NULL, discovery_id TEXT NOT NULL UNIQUE,
 first_discovered_at_us INTEGER NOT NULL, retired_at_us INTEGER,
 PRIMARY KEY(scope,platform,x_user_id)
) STRICT;
CREATE INDEX discovery_expiry ON discoveries(first_discovered_at_us);
CREATE TABLE retention_runs (
 batch_id TEXT PRIMARY KEY, completed_at_us INTEGER NOT NULL,
 manifest_sha256 TEXT NOT NULL, discoveries_deleted INTEGER NOT NULL
) STRICT;
CREATE TABLE task_outbox_next (
 id TEXT PRIMARY KEY, target TEXT UNIQUE,
 idempotency_key TEXT UNIQUE NOT NULL, request_key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
 body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt_at REAL NOT NULL DEFAULT 0, last_error TEXT, receipt_id TEXT,
 confirmed_by TEXT NOT NULL, confirmed_at REAL NOT NULL, delivered_at REAL, project_id TEXT,
 event_id TEXT, command_id TEXT, request_id TEXT, posted INTEGER NOT NULL DEFAULT 0,
 public_state TEXT NOT NULL DEFAULT 'pending', command_revision INTEGER NOT NULL DEFAULT 1, updated_at REAL,
 discovery_id TEXT, target_x_user_id TEXT, source_entity_key TEXT, body_hash TEXT, receipt_json TEXT
);
INSERT INTO task_outbox_next(id,target,idempotency_key,request_key,request_hash,body,status,attempts,next_attempt_at,last_error,receipt_id,confirmed_by,confirmed_at,delivered_at,project_id,event_id,command_id,request_id,posted,public_state,command_revision,updated_at,discovery_id,target_x_user_id,source_entity_key)
 SELECT o.id,o.target,o.idempotency_key,o.request_key,o.request_hash,o.body,o.status,o.attempts,o.next_attempt_at,o.last_error,o.receipt_id,o.confirmed_by,o.confirmed_at,o.delivered_at,o.project_id,o.event_id,o.command_id,o.request_id,o.posted,o.public_state,o.command_revision,o.updated_at,d.discovery_id,i.x_user_id,i.entity_key
 FROM task_outbox o LEFT JOIN discoveries d USING(target) LEFT JOIN target_identities i ON i.anchor=o.target;
DROP TABLE task_outbox;
ALTER TABLE task_outbox_next RENAME TO task_outbox;
CREATE UNIQUE INDEX outbox_command ON task_outbox(command_id);
CREATE UNIQUE INDEX outbox_event ON task_outbox(event_id);
CREATE UNIQUE INDEX outbox_discovery ON task_outbox(discovery_id);
