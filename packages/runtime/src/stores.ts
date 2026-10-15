import { DatabaseSync } from "node:sqlite";
import { chmodSync, existsSync, lstatSync, mkdirSync } from "node:fs";
import { isAbsolute, join, parse, resolve } from "node:path";
import type { ServiceName, StoreName } from "@ikun/contracts";

const OWNERS: Record<ServiceName, readonly StoreName[]> = {
  website: ["projects", "auth"], hunter: ["hunter"], tracking: ["tracking"],
};
const APPLICATION_IDS: Record<StoreName, number> = {
  hunter: 0x494b0201, tracking: 0x494b0202, projects: 0x494b0203, auth: 0x494b0204,
};
export interface Store { name: StoreName; path: string; db: DatabaseSync }
export interface StoreOptions { maximumVersion?: number; names?: readonly StoreName[] }
/** Refuse symlinked directories: an apparently fresh path must not alias old data. */
function rejectSymlinks(path: string): void {
  let current = parse(path).root;
  for (const part of path.slice(current.length).split("/")) {
    if (!part) continue;
    current = join(current, part);
    if (existsSync(current) && lstatSync(current).isSymbolicLink()) {
      throw new Error("SYMLINK_STORAGE_REJECTED");
    }
  }
}
function verifyMetadata(db: DatabaseSync, name: StoreName, maximumVersion: number): void {
  const columns = db.prepare('PRAGMA table_info(_schema_migrations)').all().map(row => row.name);
  if (!['version', 'name', 'applied_at'].every(column => columns.includes(column)) || columns.some(column => !['version', 'name', 'applied_at', 'checksum'].includes(String(column)))) throw new Error('UNSUPPORTED_MIGRATION_METADATA');
  if (db.prepare('SELECT store_name FROM _store_identity WHERE singleton=1').get()?.store_name !== name) throw new Error('STORE_OWNER_MISMATCH');
  if (db.prepare('SELECT name FROM _schema_migrations WHERE version=1').get()?.name !== 'foundation') throw new Error('FOUNDATION_MIGRATION_MISMATCH');
  const version = Number(db.prepare('SELECT MAX(version) AS version FROM _schema_migrations').get()?.version);
  if (!Number.isSafeInteger(version) || version < 1 || version > maximumVersion) throw new Error('UNSUPPORTED_SCHEMA_VERSION');
}
function accessStores(service: ServiceName, dataRoot: string, readOnly: boolean, options: StoreOptions): Store[] {
  if (!isAbsolute(dataRoot)) throw new Error("DATA_ROOT_MUST_BE_ABSOLUTE");
  const names = options.names ?? OWNERS[service];
  if (!names.length || new Set(names).size !== names.length || names.some(name => !OWNERS[service].includes(name))) throw new Error('STORE_OWNER_MISMATCH');
  const maximumVersion = options.maximumVersion ?? 1;
  if (!Number.isSafeInteger(maximumVersion) || maximumVersion < 1) throw new Error('INVALID_SCHEMA_VERSION');
  const root = resolve(dataRoot);
  rejectSymlinks(root);
  const opened: Store[] = [];
  try {
    for (const name of names) {
      const directory = join(root, name);
      rejectSymlinks(directory);
      if (!readOnly) mkdirSync(directory, { recursive: true, mode: 0o700 });
      const path = join(directory, `${name}.db`);
      rejectSymlinks(path);
      rejectSymlinks(`${path}-wal`);
      rejectSymlinks(`${path}-shm`);
      const existed = existsSync(path);
      if (readOnly && !existed) throw new Error('STORE_NOT_INITIALIZED');
      if (existed && lstatSync(path).nlink !== 1) throw new Error("HARDLINK_STORAGE_REJECTED");
      const db = new DatabaseSync(path, { timeout: 5000, readOnly });
      opened.push({ name, path, db });
      const marker = db.prepare("PRAGMA application_id").get()?.application_id;
      if (existed && marker !== APPLICATION_IDS[name]) throw new Error("FOREIGN_DATABASE_REJECTED");
      if (readOnly) { verifyMetadata(db, name, maximumVersion); continue; }
      const previousMetadata = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='_schema_migrations'").get();
      if (previousMetadata) verifyMetadata(db, name, maximumVersion);
      db.exec("PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;");
      db.exec(`
        BEGIN IMMEDIATE;
        PRAGMA application_id=${APPLICATION_IDS[name]};
        CREATE TABLE IF NOT EXISTS _schema_migrations (
          version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
        ) STRICT;
        CREATE TABLE IF NOT EXISTS _store_identity (
          singleton INTEGER PRIMARY KEY CHECK(singleton=1), store_name TEXT NOT NULL
        ) STRICT;
      `);
      db.prepare("INSERT OR IGNORE INTO _store_identity(singleton, store_name) VALUES (1, ?)").run(name);
      const identity = db.prepare("SELECT store_name FROM _store_identity WHERE singleton=1").get();
      if (identity?.store_name !== name) throw new Error("STORE_OWNER_MISMATCH");
      // Old Tracking candidates have an extra checksum column. Existing foundation rows
      // must not be reinserted, nor may a positional INSERT depend on the table width.
      if (!db.prepare('SELECT version FROM _schema_migrations WHERE version=1').get()) {
        db.prepare("INSERT INTO _schema_migrations(version, name, applied_at) VALUES (1, 'foundation', ?)").run(new Date().toISOString());
      }
      db.exec("COMMIT");
      chmodSync(path, 0o600);
    }
    return opened;
  } catch (error) {
    closeStores(opened);
    throw error;
  }
}
/** Explicit bootstrap/migration entry only. Never invoke this from HTTP readiness. */
export function openStores(service: ServiceName, dataRoot: string, options: StoreOptions = {}): Store[] {
  return accessStores(service, dataRoot, false, options);
}
/** Read-only, no mkdir/CREATE/ALTER/INSERT/chmod/PRAGMA mutations. */
export function inspectStores(service: ServiceName, dataRoot: string, options: StoreOptions = {}): Store[] {
  return accessStores(service, dataRoot, true, options);
}
export function storesHealthy(stores: Store[]): boolean {
  return stores.every(({ db }) => db.prepare("SELECT 1 AS ok").get()?.ok === 1);
}
export function closeStores(stores: Store[]): void {
  for (const { db } of stores) {
    try { if (db.isTransaction) db.exec("ROLLBACK"); db.close(); } catch { /* already closed */ }
  }
}
