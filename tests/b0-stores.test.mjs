import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, existsSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { inspectStores, openStores, closeStores } from '../packages/runtime/dist/index.js';

function scratch(fn) { const root = mkdtempSync('/private/tmp/ikun-b0-store-'); try { fn(root); } finally { rmSync(root, { recursive: true, force: true }); } }
test('readiness cannot create missing databases or directories', () => scratch(root => {
  assert.throws(() => inspectStores('website', root), /STORE_NOT_INITIALIZED/);
  assert.equal(existsSync(join(root, 'projects')), false);
}));
test('read-only inspection preserves bytes and cannot write; domain ownership is enforced', () => scratch(root => {
  const stores = openStores('website', root); const path = stores[0].path; closeStores(stores);
  const before = readFileSync(path); const inspected = inspectStores('website', root);
  try { assert.throws(() => inspected[0].db.exec('CREATE TABLE forbidden(id INTEGER)'), /readonly/); }
  finally { closeStores(inspected); }
  assert.deepEqual(readFileSync(path), before);
  assert.throws(() => inspectStores('hunter', root, { names: ['auth'] }), /STORE_OWNER_MISMATCH/);
}));
test('foundation reopens supported four-column Tracking metadata without positional inserts or data loss', () => scratch(root => {
  const stores = openStores('tracking', root); const path = stores[0].path; closeStores(stores);
  const legacy = new DatabaseSync(path);
  legacy.exec("ALTER TABLE _schema_migrations ADD COLUMN checksum TEXT; CREATE TABLE preserved(id INTEGER); INSERT INTO preserved VALUES(42); INSERT INTO _schema_migrations(version,name,applied_at,checksum) VALUES(2,'tracking',datetime('now'),'test-checksum');");
  legacy.close();
  assert.throws(() => openStores('tracking', root), /UNSUPPORTED_SCHEMA_VERSION/);
  const reopened = openStores('tracking', root, { maximumVersion: 2 });
  try { assert.equal(reopened[0].db.prepare('SELECT id FROM preserved').get().id, 42); assert.equal(reopened[0].db.prepare('SELECT checksum FROM _schema_migrations WHERE version=2').get().checksum, 'test-checksum'); }
  finally { closeStores(reopened); }
  const inspected = inspectStores('tracking', root, { maximumVersion: 2 }); closeStores(inspected);
}));
test('foreign owner and unsupported metadata fail before mutation', () => scratch(root => {
  const stores = openStores('hunter', root); const path = stores[0].path; closeStores(stores);
  const malformed = new DatabaseSync(path); malformed.exec('ALTER TABLE _schema_migrations ADD COLUMN unexpected TEXT'); malformed.close();
  const before = readFileSync(path);
  assert.throws(() => openStores('hunter', root), /UNSUPPORTED_MIGRATION_METADATA/);
  assert.deepEqual(readFileSync(path), before);
}));
test('actual frozen Tracking migration upgrades a temporary foundation and reopens compatibly', () => scratch(root => {
  const stores = openStores('tracking', root); const path = stores[0].path; closeStores(stores);
  const source = join(root, 'pinned-migration'); mkdirSync(source);
  for (const file of ['store.py', 'schema.sql']) writeFileSync(join(source, file), execFileSync('git', ['show', `9e2835cafc95cb15dc4b8178abacf0c604018536:services/tracking-worker/python/tracking/${file}`]));
  execFileSync('python3', ['-c', 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[2]); from store import Store; Store(Path(sys.argv[1]))', path, source], { stdio: 'pipe' });
  const upgraded = inspectStores('tracking', root, { maximumVersion: 2 });
  try { assert.equal(upgraded[0].db.prepare('SELECT MAX(version) AS v FROM _schema_migrations').get().v, 2); }
  finally { closeStores(upgraded); }
  const reopened = openStores('tracking', root, { maximumVersion: 2 }); closeStores(reopened);
}));
