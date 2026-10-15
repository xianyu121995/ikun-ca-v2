CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
    rating TEXT NOT NULL DEFAULT 'unrated' CHECK(rating IN ('S','A','B','unrated')),
    description TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    website_key TEXT,
    notes TEXT NOT NULL DEFAULT '',
    progress TEXT NOT NULL DEFAULT 'todo' CHECK(progress IN ('todo','researching','watching','participating','completed','paused')),
    token_date TEXT,
    token_date_status TEXT NOT NULL DEFAULT 'unconfirmed' CHECK(token_date_status IN ('confirmed','estimated','unconfirmed')),
    discovered_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    deleted_at TEXT,
    CHECK((token_date IS NULL AND token_date_status='unconfirmed') OR (token_date IS NOT NULL AND token_date_status IN ('confirmed','estimated'))),
    UNIQUE(tenant_id, website_key)
);
CREATE INDEX projects_active_updated ON projects(deleted_at, updated_at DESC, id);
CREATE INDEX projects_active_rating ON projects(deleted_at, rating, id);
CREATE INDEX projects_active_progress ON projects(deleted_at, progress, id);
CREATE TABLE project_sources (
    tenant_id TEXT NOT NULL DEFAULT 'default',
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id),
    added_by TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY(tenant_id, source, external_id)
);
CREATE TABLE principals (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    token_hash TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK(kind IN ('user','service')),
    role TEXT CHECK(role IN ('superadmin','user')),
    source TEXT,
    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)),
    created_at TEXT NOT NULL,
    CHECK((kind='service' AND role IS NULL AND source IS NOT NULL) OR (kind='user' AND role IS NOT NULL AND source IS NULL))
);
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL REFERENCES principals(id),
    csrf_hash TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE write_receipts (
    principal_id TEXT NOT NULL REFERENCES principals(id),
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY(principal_id, idempotency_key)
);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id),
    changed_fields TEXT NOT NULL,
    created_at TEXT NOT NULL
);
