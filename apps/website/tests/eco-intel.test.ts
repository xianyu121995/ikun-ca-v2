import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { isIntelRead } from '../lib/eco-intel/access.ts';
import { DEFAULT_SEEDS } from '../lib/eco-intel/fixtures.ts';
import { handleIntel } from '../lib/eco-intel/http.ts';
import { acceptProviderEvent } from '../lib/eco-intel/pipeline.ts';
import { classifyTweet, followDisposition } from '../lib/eco-intel/rules.ts';
import { INTEL_MIGRATION_SQL } from '../lib/eco-intel/schema.ts';
import { openIntelStore } from '../lib/eco-intel/store.ts';

function tempStore() {
  const root = mkdtempSync(join(tmpdir(), 'eco-intel-'));
  const store = openIntelStore(join(root, 'intel', 'intel.db'));
  return { root, store };
}

test('schema file matches the inlined migration', () => {
  const file = readFileSync(new URL('../../../schemas/intel/001_eco_intel.sql', import.meta.url), 'utf8');
  assert.equal(file, INTEL_MIGRATION_SQL);
});

test('tweet keywords and follow types follow the intel rules', () => {
  assert.deepEqual(classifyTweet('黑客松现场宣布新协议上线，并完成融资，准备发射').topics, ['hackathon', 'launch', 'protocol', 'launchpad', 'raise']);
  assert.equal(classifyTweet('gm builders').push_to_feed, false);
  assert.equal(followDisposition('protocol').promote_suggested, true);
  assert.equal(followDisposition('launchpad').watch_tweets, true);
  assert.equal(followDisposition('hackathon').promote_suggested, true);
  assert.equal(followDisposition('founder').promote_suggested, false);
  assert.equal(followDisposition('token').watch_tweets, false);
  assert.equal(followDisposition('unrelated').promote_suggested, false);
});

test('read routes are public to logged-in readers and writes are not', () => {
  assert.equal(isIntelRead('GET', '/intel'), true);
  assert.equal(isIntelRead('GET', '/intel/tweets'), true);
  assert.equal(isIntelRead('GET', '/intel/follows'), true);
  assert.equal(isIntelRead('GET', '/api/v1/intel/seeds'), true);
  assert.equal(isIntelRead('GET', '/api/v1/intel/follows/fol_1/promote'), true);
  assert.equal(isIntelRead('POST', '/api/v1/intel/seeds'), false);
  assert.equal(isIntelRead('GET', '/api/v1/hunter/signals'), false);
  assert.equal(isIntelRead('GET', '/hunter'), false);
});

test('fresh intel.db seeds fixtures once and stays separate from the four stores', () => {
  const { root, store } = tempStore();
  try {
    const mode = statSync(store.path).mode & 0o777;
    assert.equal(mode, 0o600);
    const first = store.listSeeds('', 100);
    assert.equal(first.items.length, DEFAULT_SEEDS.length);
    assert.equal(first.next_cursor, null);
    assert.ok(first.items.some(row => row.x_handle.toLowerCase() === 'bnbchain' && row.source === 'fixture'));
    const tweets = store.listTweets('', 20);
    assert.equal(tweets.items.find(row => row.tweet_id === 'tw_fixture_hackathon')?.push_to_feed, true);
    assert.equal(tweets.items.find(row => row.tweet_id === 'tw_fixture_noise')?.push_to_feed, false);
    const follows = store.listFollows('', '', 20);
    assert.equal(follows.items.find(row => row.follow_id === 'fol_fixture_protocol')?.promote_suggested, true);
    assert.equal(follows.items.find(row => row.follow_id === 'fol_fixture_person')?.promote_suggested, false);
    store.close();
    const again = openIntelStore(store.path);
    assert.equal(again.listSeeds('', 100).items.length, DEFAULT_SEEDS.length);
    again.close();
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('seed crud, follow promotion and provider queue stay inside intel.db', async () => {
  const { root, store } = tempStore();
  try {
    const admin = { user_id: 'admin', role: 'superadmin' as const };
    const reader = { user_id: 'reader', role: 'user' as const };
    const denied = await handleIntel(store, reader, new Request('http://127.0.0.1/api/v1/intel/seeds', {
      method: 'POST', headers: { 'content-type': 'application/json', 'idempotency-key': 'reader-key-1' }, body: '{}',
    }));
    assert.equal(denied.status, 403);

    const created = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/seeds', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': 'seed-key-01' },
      body: JSON.stringify({ x_handle: '@NewSeed', ecosystem: 'base', role_label: '官方', notes: 'manual', enabled: true }),
    }));
    assert.equal(created.status, 201);
    const seed = (await created.json()).data;
    const replay = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/seeds', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': 'seed-key-01' },
      body: JSON.stringify({ x_handle: '@NewSeed', ecosystem: 'base', role_label: '官方', notes: 'manual', enabled: true }),
    }));
    assert.equal(replay.status, 201);
    assert.equal((await replay.json()).data.seed_id, seed.seed_id);
    assert.equal(store.listSeeds('newseed', 10).items.length, 1);

    const clash = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/seeds', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': 'seed-key-01' },
      body: JSON.stringify({ x_handle: '@Other', ecosystem: 'eth', role_label: '官方', notes: '', enabled: true }),
    }));
    assert.equal(clash.status, 409);

    const stale = await handleIntel(store, admin, new Request(`http://127.0.0.1/api/v1/intel/seeds/${seed.seed_id}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json', 'idempotency-key': 'seed-patch-1', 'if-match': '"rev-9"' },
      body: JSON.stringify({ notes: 'changed' }),
    }));
    assert.equal(stale.status, 409);

    const patched = await handleIntel(store, admin, new Request(`http://127.0.0.1/api/v1/intel/seeds/${seed.seed_id}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json', 'idempotency-key': 'seed-patch-2', 'if-match': '"rev-1"' },
      body: JSON.stringify({ notes: 'changed', enabled: false }),
    }));
    assert.equal(patched.status, 200);
    assert.equal((await patched.json()).data.notes, 'changed');

    const tweet = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/tweets', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': 'tweet-key-1' },
      body: JSON.stringify({ x_handle: 'NewSeed', text: '测试网上线', url: 'https://example.invalid/launch' }),
    }));
    assert.equal(tweet.status, 201);
    assert.equal((await tweet.json()).data.push_to_feed, true);

    const follow = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/follows', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': 'follow-key-1' },
      body: JSON.stringify({ x_handle: 'chainproject', seed_handle: 'solana', account_type: 'protocol', bio: 'fixture bio', recent_summary: 'summary' }),
    }));
    assert.equal(follow.status, 201);
    const followBody = (await follow.json()).data;
    assert.equal(followBody.promote_suggested, true);
    const promoted = await handleIntel(store, admin, new Request(`http://127.0.0.1/api/v1/intel/follows/${followBody.follow_id}/promote`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': 'promote-key-1', 'if-match': '"rev-1"' },
      body: '{}',
    }));
    assert.equal(promoted.status, 200);
    const promotedBody = (await promoted.json()).data;
    assert.equal(promotedBody.follow.status, 'promoted');
    assert.equal(promotedBody.seed.x_handle.toLowerCase(), 'chainproject');
    assert.equal(promotedBody.seed.ecosystem, 'solana');

    const removed = await handleIntel(store, admin, new Request(`http://127.0.0.1/api/v1/intel/seeds/${seed.seed_id}`, {
      method: 'DELETE',
      headers: { 'content-type': 'application/json', 'idempotency-key': 'seed-del-01', 'if-match': '"rev-2"' },
      body: '{}',
    }));
    assert.equal(removed.status, 200);
    assert.equal(store.getSeed(seed.seed_id), null);
    assert.equal(store.listTweets('newseed', 10).items[0]?.seed_id, null);

    const queued = acceptProviderEvent(store, 'wss_follow', { handle: 'chainproject', seed_handle: 'solana' });
    assert.equal(queued.status, 'pending');
    assert.equal(queued.kind, 'wss_follow');
    await assert.rejects(() => Promise.resolve().then(() => acceptProviderEvent(store, 'wss_tweet', { api_key: 'nope' })), /凭据/);
    const pipeline = readFileSync(new URL('../lib/eco-intel/pipeline.ts', import.meta.url), 'utf8');
    assert.match(pipeline, /TODO\(6551\)/);
    assert.match(pipeline, /must not call/);
    assert.doesNotMatch(pipeline, /fetch\(|from ['"]node:https|6551\.io/);
  } finally {
    store.close();
    rmSync(root, { recursive: true, force: true });
  }
});

test('a foreign sqlite file is refused', () => {
  const root = mkdtempSync(join(tmpdir(), 'eco-intel-foreign-'));
  const path = join(root, 'intel', 'intel.db');
  try {
    mkdirSync(join(root, 'intel'), { recursive: true });
    const db = new DatabaseSync(path);
    db.exec('PRAGMA application_id=1228874244');
    db.close();
    assert.throws(() => openIntelStore(path), /INTEL_FOREIGN_DATABASE_REJECTED/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
