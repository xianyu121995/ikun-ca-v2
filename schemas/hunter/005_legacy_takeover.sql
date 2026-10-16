-- Owned by the sole Hunter migrator and _migration_checksums registry.
-- Additive schema 5; no service request or importer executes this DDL.
CREATE TABLE hunter_takeover_runs (
 package_sha256 TEXT PRIMARY KEY, execution_id TEXT NOT NULL,
 source_sha256 TEXT NOT NULL, ownership_sha256 TEXT NOT NULL, projects_sha256 TEXT NOT NULL,
 effective_at_us INTEGER NOT NULL, completed_at_us INTEGER NOT NULL,
 report_json TEXT NOT NULL
) STRICT;
CREATE TABLE hunter_takeover_rows (
 source_system TEXT NOT NULL CHECK(source_system='legacy-hunter'),
 source_table TEXT NOT NULL, source_key_sha256 TEXT NOT NULL,
 row_sha256 TEXT NOT NULL, outcome TEXT NOT NULL
 CHECK(outcome IN ('imported','deduplicated','quarantined','excluded')),
 reason TEXT NOT NULL, target_ref TEXT, package_sha256 TEXT NOT NULL,
 PRIMARY KEY(source_system,source_table,source_key_sha256),
 FOREIGN KEY(package_sha256) REFERENCES hunter_takeover_runs(package_sha256)
 DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE hunter_takeover_baselines (
 hunter_id TEXT PRIMARY KEY REFERENCES hunters(id), source_sha256 TEXT NOT NULL,
 snapshot_sha256 TEXT NOT NULL, snapshot_count INTEGER NOT NULL,
 first_seen_at_us INTEGER, last_seen_at_us INTEGER, last_success_at_us INTEGER,
 ready_proven INTEGER NOT NULL CHECK(ready_proven IN (0,1))
) STRICT;
CREATE TABLE hunter_takeover_conflicts (
 package_sha256 TEXT NOT NULL, source_table TEXT NOT NULL, source_key_sha256 TEXT NOT NULL,
 row_sha256 TEXT NOT NULL, prior_row_sha256 TEXT NOT NULL, reason TEXT NOT NULL,
 PRIMARY KEY(package_sha256,source_table,source_key_sha256),
 FOREIGN KEY(package_sha256) REFERENCES hunter_takeover_runs(package_sha256)
 DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE hunter_takeover_seen_times (
 hunter_id TEXT NOT NULL REFERENCES hunters(id), generation INTEGER NOT NULL,
 target TEXT NOT NULL COLLATE NOCASE, x_user_id TEXT NOT NULL,
 first_seen_at_us INTEGER NOT NULL, last_seen_at_us INTEGER NOT NULL,
 PRIMARY KEY(hunter_id,generation,x_user_id),
 FOREIGN KEY(hunter_id,generation,target) REFERENCES seen_targets(hunter_id,generation,target) ON DELETE CASCADE
) STRICT;
CREATE TABLE hunter_takeover_project_refs (
 x_user_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, map_sha256 TEXT NOT NULL
) STRICT;
