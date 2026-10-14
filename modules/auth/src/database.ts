import { createHash } from "node:crypto";
import { chmodSync, existsSync, lstatSync, mkdirSync, openSync, closeSync } from "node:fs";
import { join, parse, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import type { AuthConfig } from "./config.js";

export const APP_ID = 0x494b0204;
const migration = `
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
`;
const checksum = createHash("sha256").update(migration).digest("hex");

function noLinks(path: string, regular = false) {
  let current = parse(path).root;
  for (const part of path.slice(current.length).split("/")) {
    if (!part) continue;
    current = join(current, part);
    if (existsSync(current) && lstatSync(current).isSymbolicLink()) throw new Error("AUTH_SYMLINK_REJECTED");
  }
  if (regular && existsSync(path) && (!lstatSync(path).isFile() || lstatSync(path).nlink !== 1))
    throw new Error("AUTH_FILE_ALIAS_REJECTED");
}

/** Opens auth/auth.db only. Migrations must be explicitly requested by the CLI. */
export function database(cfg: AuthConfig, migrate = false): DatabaseSync {
  const directory = join(resolve(cfg.dataRoot), "auth"), path = join(directory, "auth.db");
  noLinks(path, true); noLinks(path + "-wal", true); noLinks(path + "-shm", true);
  if (!existsSync(path) && !migrate) throw new Error("AUTH_MIGRATION_REQUIRED");
  if (existsSync(path)) {
    // A read-only preflight precedes chmod and any WAL/DDL modifications.
    const existing = new DatabaseSync(path, {readOnly: true, timeout: 5000});
    try {
      if (existing.prepare("PRAGMA application_id").get()?.application_id !== APP_ID ||
          existing.prepare("SELECT store_name FROM _store_identity WHERE singleton=1").get()?.store_name !== "auth")
        throw new Error("AUTH_FOREIGN_DATABASE_REJECTED");
    } finally { existing.close(); }
  } else {
    mkdirSync(directory, {recursive: true, mode: 0o700});
    closeSync(openSync(path, "wx", 0o600));
  }
  const db = new DatabaseSync(path, {timeout: 5000});
  try {
    chmodSync(directory, 0o700); chmodSync(path, 0o600);
    db.exec("PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;");
    db.exec("BEGIN IMMEDIATE");
    if (db.prepare("PRAGMA application_id").get()?.application_id === 0) {
      db.exec(`PRAGMA application_id=${APP_ID};
        CREATE TABLE _schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL) STRICT;
        CREATE TABLE _store_identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1), store_name TEXT NOT NULL) STRICT;
        INSERT INTO _store_identity VALUES(1,'auth');`);
      db.prepare("INSERT INTO _schema_migrations VALUES(1,'foundation',?)").run(new Date().toISOString());
    }
    const version = db.prepare("SELECT max(version) AS version FROM _schema_migrations").get()?.version;
    if (version === 1 && migrate) {
      db.exec(migration);
      db.prepare("INSERT INTO auth_site_scope VALUES(1,?)").run(cfg.tenantId);
      db.prepare("INSERT INTO auth_migration_checksums VALUES(2,?)").run(checksum);
      db.prepare("INSERT INTO _schema_migrations VALUES(2,'auth_accounts_v1',?)").run(new Date().toISOString());
    } else if (version !== 2) throw new Error("AUTH_MIGRATION_REQUIRED");
    if (db.prepare("SELECT checksum FROM auth_migration_checksums WHERE version=2").get()?.checksum !== checksum)
      throw new Error("AUTH_MIGRATION_CHECKSUM_MISMATCH");
    if (db.prepare("SELECT tenant_id FROM auth_site_scope WHERE singleton=1").get()?.tenant_id !== cfg.tenantId)
      throw new Error("AUTH_SCOPE_MISMATCH");
    db.exec("COMMIT");
    return db;
  } catch (error) {
    if (db.isTransaction) db.exec("ROLLBACK");
    db.close(); throw error;
  }
}
