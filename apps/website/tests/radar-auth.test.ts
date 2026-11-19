import {mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AuthHttp} from '../../../modules/auth/dist/src/http.js';
import {config, cookieName} from '../../../modules/auth/dist/src/config.js';
import {LocalAccounts} from '../../../modules/auth/dist/src/local.js';
import {RADAR_READ_API, RADAR_READ_PAGES} from '../lib/radar-view.ts';

const origin = 'http://127.0.0.1:4011';
const initial = 'unit-test-initial-long-passphrase';
const active = 'unit-test-active-long-passphrase';

async function fixture() {
  const directory = mkdtempSync(join(tmpdir(), 'ikun-radar-auth-'));
  const cfg = config({dataRoot: directory, origin, secure: false});
  const store = new LocalAccounts(cfg, true, () => 1_800_000_000);
  await store.bootstrap('root_admin', initial);
  const first = await store.login('root_admin', initial);
  const root = await store.changePassword(first.actor, initial, active);
  await store.create('viewer_one', initial);
  const viewerFirst = await store.login('viewer_one', initial);
  const viewer = await store.changePassword(viewerFirst.actor, initial, active);
  await store.create('viewer_two', initial);
  const otherFirst = await store.login('viewer_two', initial);
  const other = await store.changePassword(otherFirst.actor, initial, active);
  const http = new AuthHttp(store, [...RADAR_READ_API], [...RADAR_READ_PAGES]);
  return {directory, store, http, root, viewer, other};
}

function request(path: string, token?: string, extra: Record<string, string> = {}, method = 'GET') {
  const headers: Record<string, string> = {host: '127.0.0.1:4011', ...extra};
  if (token) headers.cookie = `${cookieName(config({dataRoot: '/tmp', origin, secure: false}))}=${token}`;
  return new Request(origin + path, {method, headers});
}

test('radar pages and reads stay inside the existing session and tenant', async () => {
  const env = await fixture();
  try {
    assert.equal(env.http.gate(request('/radar'))?.status, 303);
    assert.equal(env.http.gate(request('/api/v1/radar/snapshot'))?.status, 401);
    assert.equal(env.http.gate(request('/radar', env.viewer.token)), null);
    assert.equal(env.http.gate(request('/prototypes/radar', env.viewer.token)), null);
    assert.equal(env.http.gate(request('/api/v1/radar/snapshot', env.viewer.token)), null);
    assert.equal(env.http.gate(request('/api/v1/radar/events', env.viewer.token)), null);
    assert.equal(env.http.gate(request('/api/v1/radar/snapshot', env.root.token)), null);
    assert.equal(env.http.gate(request('/api/v1/radar/snapshot', env.viewer.token, {}, 'POST'))?.status, 403);
    assert.equal(env.http.gate(request('/api/v1/radar/snapshot?tenant_id=other', env.viewer.token))?.status, 403);
    assert.equal(env.http.gate(request('/api/v1/radar/events', env.viewer.token, {'x-tenant': 'other'}))?.status, 403);
    assert.equal(env.http.gate(request('/api/v1/hunter/accounts', env.viewer.token))?.status, 403);
    const viewer = env.http.authorize(request('/api/v1/radar/snapshot', env.viewer.token), false);
    const other = env.http.authorize(request('/api/v1/radar/snapshot', env.other.token), false);
    assert.notEqual(viewer.id, other.id);
    assert.equal(viewer.tenant_id, 'ikun-main');
    assert.equal(env.http.gate(request('/api/v1/radar/snapshot', 'not-a-session'))?.status, 401);
  } finally {
    env.store.close();
    rmSync(env.directory, {recursive: true, force: true});
  }
});
