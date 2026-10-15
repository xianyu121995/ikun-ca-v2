ALTER TABLE hunters ADD COLUMN label TEXT NOT NULL DEFAULT '';
ALTER TABLE hunters ADD COLUMN baseline_at REAL;
ALTER TABLE discoveries ADD COLUMN discovery_id TEXT;
ALTER TABLE discoveries ADD COLUMN project_json TEXT;
ALTER TABLE discoveries ADD COLUMN updated_at REAL;
CREATE UNIQUE INDEX discovery_identity ON discoveries(discovery_id);
ALTER TABLE task_outbox ADD COLUMN event_id TEXT;
ALTER TABLE task_outbox ADD COLUMN command_id TEXT;
ALTER TABLE task_outbox ADD COLUMN request_id TEXT;
ALTER TABLE task_outbox ADD COLUMN posted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE task_outbox ADD COLUMN public_state TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE task_outbox ADD COLUMN command_revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE task_outbox ADD COLUMN updated_at REAL;
CREATE UNIQUE INDEX outbox_command ON task_outbox(command_id);
CREATE UNIQUE INDEX outbox_event ON task_outbox(event_id);
CREATE TABLE target_identities (
 entity_key TEXT PRIMARY KEY, anchor TEXT UNIQUE NOT NULL,
 x_user_id TEXT UNIQUE, current_handle TEXT NOT NULL, updated_at REAL NOT NULL
) STRICT;
CREATE TABLE target_aliases (
 x_handle TEXT PRIMARY KEY, entity_key TEXT NOT NULL REFERENCES target_identities(entity_key)
) STRICT;
CREATE TABLE operation_receipts (
 actor_id TEXT NOT NULL, scope TEXT NOT NULL CHECK(scope='ikun-main'),
 route TEXT NOT NULL, request_key TEXT NOT NULL, body_hash TEXT NOT NULL,
 status INTEGER NOT NULL, response_json TEXT NOT NULL, etag TEXT,
 created_at REAL NOT NULL, expires_at REAL NOT NULL,
 PRIMARY KEY(actor_id,scope,route,request_key)
) STRICT;
CREATE TABLE public_changes (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL,
 entity_id TEXT NOT NULL, data TEXT NOT NULL, received_at REAL NOT NULL
) STRICT;
