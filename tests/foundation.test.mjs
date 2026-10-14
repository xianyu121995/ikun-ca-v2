import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, statSync, symlinkSync, linkSync } from 'node:fs';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { openStores, closeStores, storesHealthy, requestId, validBearer } from '../packages/runtime/dist/index.js';
import { newProjectId, parseProjectId } from '../packages/contracts/dist/index.js';

const scratch = fn => {
  const root = mkdtempSync('/private/tmp/ikun-ca-v2-test-');
  try { fn(root); } finally { rmSync(root, { recursive: true, force: true }); }
};
test('service ownership, physical separation and repeatable migration', () => scratch(root => {
  const website = openStores('website', root);
  const hunter = openStores('hunter', root);
  const tracking = openStores('tracking', root);
  const stores = [...website, ...hunter, ...tracking];
  try {
    assert.deepEqual(website.map(s => s.name), ['projects', 'auth']);
    assert.deepEqual(hunter.map(s => s.name), ['hunter']);
    assert.deepEqual(tracking.map(s => s.name), ['tracking']);
    assert.equal(new Set(stores.map(s => statSync(s.path).ino)).size, 4);
    assert.ok(storesHealthy(stores));
    for (const store of stores) {
      assert.equal(store.db.prepare('PRAGMA journal_mode').get().journal_mode, 'wal');
      assert.equal(store.db.prepare('PRAGMA foreign_keys').get().foreign_keys, 1);
      assert.equal(statSync(store.path).mode & 0o777, 0o600);
      assert.equal(store.db.prepare('SELECT COUNT(*) AS n FROM _schema_migrations').get().n, 1);
    }
  } finally { closeStores(stores); }
  const reopened = openStores('website', root);
  try { assert.equal(reopened[0].db.prepare('SELECT COUNT(*) AS n FROM _schema_migrations').get().n, 1); }
  finally { closeStores(reopened); }
}));
test('foreign database is rejected without changing its marker or tables', () => scratch(root => {
  const stores = openStores('hunter', root);
  const path = stores[0].path;
  closeStores(stores);
  const foreign = new DatabaseSync(path);
  foreign.exec('PRAGMA application_id=0; CREATE TABLE legacy (id INTEGER)');
  foreign.close();
  assert.throws(() => openStores('hunter', root), /FOREIGN_DATABASE_REJECTED/);
  const verify = new DatabaseSync(path, { readOnly: true });
  try { assert.equal(verify.prepare('PRAGMA application_id').get().application_id, 0); }
  finally { verify.close(); }
}));
test('symlink and hardlink aliases cannot cross store boundaries', () => scratch(root => {
  const stores = openStores('hunter', root);
  const path = stores[0].path;
  closeStores(stores);
  symlinkSync(join(root, 'hunter'), join(root, 'tracking'));
  assert.throws(() => openStores('tracking', root), /SYMLINK_STORAGE_REJECTED/);
  linkSync(path, join(root, 'alias.db'));
  assert.throws(() => openStores('hunter', root), /HARDLINK_STORAGE_REJECTED/);
}));
test('service credential checks fail closed', () => {
  const token = 'a'.repeat(64);
  assert.equal(validBearer(`Bearer ${token}`, undefined), false);
  assert.equal(validBearer('Bearer short', 'short'), false);
  assert.equal(validBearer(`Bearer ${token}`, token), true);
  assert.equal(validBearer(`Bearer ${'b'.repeat(64)}`, token), false);
  assert.equal(validBearer(`Basic ${token}`, token), false);
});
test('project ID format is canonical and request IDs cannot carry injected text', () => {
  const id = newProjectId();
  assert.equal(parseProjectId(id), id);
  assert.throws(() => parseProjectId('twitter-handle'), TypeError);
  assert.throws(() => parseProjectId('prj_00000000-0000-7000-8000-000000000000'), TypeError);
  assert.equal(requestId('trace_123'), 'trace_123');
  assert.notEqual(requestId('private\nheader'), 'private\nheader');
});
