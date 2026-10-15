CREATE TABLE projects (
 id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL DEFAULT 'ikun-main',
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
 rating TEXT NOT NULL DEFAULT 'unrated' CHECK(rating IN ('S','A','B','C','D','unrated')),
 description TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '', website_key TEXT,
 notes TEXT NOT NULL DEFAULT '', category TEXT,
 progress TEXT NOT NULL DEFAULT 'todo' CHECK(progress IN ('todo','researching','watching','participating','completed','paused')),
 progress_percent REAL CHECK(progress_percent IS NULL OR (progress_percent>=0 AND progress_percent<=100)),
 token_date TEXT, token_date_status TEXT NOT NULL DEFAULT 'unconfirmed' CHECK(token_date_status IN ('confirmed','estimated','unconfirmed')),
 home_membership TEXT NOT NULL DEFAULT 'active' CHECK(home_membership IN ('hidden','active','removed')),
 discovered_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1 CHECK(version>0), deleted_at TEXT,
 UNIQUE(tenant_id,website_key),
 CHECK((token_date IS NULL AND token_date_status='unconfirmed') OR (token_date IS NOT NULL AND token_date_status IN ('confirmed','estimated')))
);
CREATE TABLE project_sources (
 tenant_id TEXT NOT NULL, source TEXT NOT NULL, external_id TEXT NOT NULL,
 project_id TEXT NOT NULL REFERENCES projects(id), added_by TEXT NOT NULL, added_at TEXT NOT NULL,
 PRIMARY KEY(tenant_id,source,external_id)
);
CREATE TABLE audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
 actor_id TEXT NOT NULL, action TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
 changed_fields TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE operation_receipts (
 actor_id TEXT NOT NULL, tenant_id TEXT NOT NULL, route TEXT NOT NULL, idempotency_key TEXT NOT NULL,
 body_hash TEXT NOT NULL, response_json TEXT NOT NULL, status INTEGER NOT NULL,
 created_at TEXT NOT NULL, expires_at INTEGER NOT NULL,
 original_request_id TEXT NOT NULL, method TEXT NOT NULL, path TEXT NOT NULL, contract TEXT NOT NULL,
 PRIMARY KEY(actor_id,tenant_id,route,idempotency_key)
);
CREATE TABLE event_inbox (
 source TEXT NOT NULL, event_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
 body_hash TEXT NOT NULL, project_id TEXT REFERENCES projects(id), command_id TEXT,
 receipt_id TEXT NOT NULL, accepted_at TEXT NOT NULL,
 PRIMARY KEY(tenant_id,source,event_id)
);
CREATE TABLE tracking_outbox (
 command_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
 command_json TEXT NOT NULL, command_hash TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','sending','accepted','running','succeeded','failed','unknown')),
 attempts INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0,1)), lease_until INTEGER, lease_token TEXT,
 remote_json TEXT, error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE project_changes (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
 tenant_id TEXT NOT NULL, record_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE project_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE project_milestones (
 project_id TEXT PRIMARY KEY REFERENCES projects(id), date TEXT, hour TEXT, title TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'unconfirmed' CHECK(status IN ('confirmed','estimated','unconfirmed'))
);
CREATE TABLE project_completions (
 completion_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 previous_stage TEXT NOT NULL, previous_percent REAL, completed_at TEXT NOT NULL,
 restore_basis TEXT NOT NULL CHECK(restore_basis IN ('persisted','creation_default')), restored_at TEXT
);
CREATE UNIQUE INDEX completion_current ON project_completions(project_id) WHERE restored_at IS NULL;
CREATE INDEX projects_scope_updated ON projects(tenant_id,home_membership,updated_at,id);
CREATE INDEX projects_scope_discovered ON projects(tenant_id,home_membership,discovered_at,id);
CREATE INDEX projects_scope_rating ON projects(tenant_id,home_membership,rating,id);
CREATE INDEX sources_canonical ON project_sources(project_id);
CREATE INDEX outbox_dispatch ON tracking_outbox(state,lease_until,updated_at);
CREATE INDEX changes_scope ON project_changes(tenant_id,sequence);
