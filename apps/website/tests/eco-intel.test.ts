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
import { classifyFollow, classifyTweet, followDisposition } from '../lib/eco-intel/rules.ts';
import { INTEL_MIGRATION_SQL, INTEL_PROJECTS_SQL } from '../lib/eco-intel/schema.ts';
import { TRACKING_CREATE_ROUTE, commandId, trackingCreateCommand } from '../lib/tracking-command.ts';
import { openIntelStore } from '../lib/eco-intel/store.ts';

function tempStore() {
  const root = mkdtempSync(join(tmpdir(), 'eco-intel-'));
  const store = openIntelStore(join(root, 'intel', 'intel.db'));
  return { root, store };
}

test('schema file matches the inlined migration', () => {
  const file = readFileSync(new URL('../../../schemas/intel/001_eco_intel.sql', import.meta.url), 'utf8');
  assert.equal(file, INTEL_MIGRATION_SQL);
  const projects = readFileSync(new URL('../../../schemas/intel/002_eco_intel_projects.sql', import.meta.url), 'utf8');
  assert.equal(projects, INTEL_PROJECTS_SQL);
});

test('tweet keywords and follow types follow the intel rules', () => {
  assert.deepEqual(classifyTweet('黑客松现场宣布新协议上线，并完成融资，准备发射').topics, ['hackathon', 'launch', 'protocol', 'launchpad', 'raise']);
  assert.equal(classifyTweet('gm builders').push_to_feed, false);
  assert.equal(followDisposition('protocol', 'solana').promote_suggested, true);
  assert.equal(followDisposition('protocol', 'solana').classification, 'project');
  assert.equal(followDisposition('protocol', 'solana').auto_track, false);
  assert.equal(followDisposition('protocol').classification, 'pending');
  assert.equal(followDisposition('launchpad', 'base').watch_tweets, true);
  assert.equal(followDisposition('hackathon', 'robinhood').promote_suggested, true);
  assert.equal(followDisposition('founder').promote_suggested, false);
  assert.equal(followDisposition('token', 'bsc').watch_tweets, false);
  assert.equal(followDisposition('token', 'bsc').classification, 'noise');
  assert.equal(followDisposition('token', 'bsc').track_eligible, false);
  assert.equal(followDisposition('kol', 'eth').classification, 'noise');
  assert.equal(followDisposition('unrelated').promote_suggested, false);
  const inferred = classifyFollow({ accountType: 'unclassified', chain: '', bio: 'DeFi protocol and oracle on Solana', recentSummary: 'bridge' });
  assert.equal(inferred.accountType, 'protocol');
  assert.equal(inferred.chain, 'solana');
  assert.equal(inferred.classification, 'project');
  assert.equal(inferred.auto_track, false);
  const token = classifyFollow({ accountType: 'unclassified', chain: 'bsc', bio: 'memecoin protocol on BSC', recentSummary: '' });
  assert.equal(token.accountType, 'token');
  assert.equal(token.classification, 'noise');
  assert.equal(token.promote_suggested, false);
  assert.equal(classifyFollow({ accountType: 'unclassified', chain: '', bio: '?', recentSummary: '' }).classification, 'pending');
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
    assert.equal(follows.items.find(row => row.follow_id === 'fol_fixture_protocol')?.chain, 'solana');
    assert.equal(follows.items.find(row => row.follow_id === 'fol_fixture_person')?.promote_suggested, false);
    assert.equal(follows.items.find(row => row.follow_id === 'fol_fixture_token')?.classification, 'noise');
    assert.equal(follows.items.find(row => row.follow_id === 'fol_fixture_pending')?.status, 'pending');
    const projects = store.listFollows('', '', 50, undefined, { view: 'projects' });
    assert.equal(projects.items.some(row => row.account_type === 'token'), false);
    assert.equal(new Set(projects.items.filter(row => row.classification === 'project').map(row => row.chain)).size, 5);
    const bsc = store.listFollows('', '', 50, undefined, { view: 'projects', chain: 'bsc' });
    assert.ok(bsc.items.some(row => row.follow_id === 'fol_fixture_bsc_protocol'));
    assert.equal(bsc.items.some(row => row.follow_id === 'fol_fixture_token'), false);
    assert.equal((store.db.prepare('SELECT COUNT(*) AS n FROM intel_track_outbox').get() as { n: number }).n, 0);
    assert.equal((store.db.prepare('PRAGMA user_version').get() as { user_version: number }).user_version, 3);
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

test('项目追踪 enqueues tracking.create and never auto-promotes a token', async () => {
  const { root, store } = tempStore();
  try {
    const admin = { user_id: 'admin', role: 'superadmin' as const };
    const calls: { confirmed: unknown; handle: unknown; key: string }[] = [];
    const submit = async (input: { idempotencyKey: string; body: { name: string; x_handle: string; x_user_id: string | null; notes: string; confirmed: true; project_id?: string } }) => {
      calls.push({ confirmed: input.body.confirmed, handle: input.body.x_handle, key: input.idempotencyKey });
      const command = trackingCreateCommand({
        actor: { user_id: 'admin', tenant_id: 'ikun-main', role: 'superadmin' },
        route: TRACKING_CREATE_ROUTE,
        idempotencyKey: input.idempotencyKey,
        projectId: 'prj_11111111-1111-4111-8111-111111111111',
        name: input.body.name,
        xUserId: input.body.x_user_id,
        xHandle: input.body.x_handle,
        notes: input.body.notes,
        issuedAt: '2026-10-26T01:00:00.000Z',
      });
      return { ok: true, status: 202, command, remoteState: 'accepted', error: '' };
    };
    const token = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/follows/fol_fixture_token/track', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': '11111111-1111-4111-8111-111111111111', 'if-match': '"rev-1"' },
      body: JSON.stringify({ confirmed: true }),
    }), { submitTracking: submit });
    assert.equal(token.status, 409);
    assert.equal(calls.length, 0);
    assert.equal(store.trackCommand('fol_fixture_token'), null);

    const key = '22222222-2222-4222-8222-222222222222';
    const tracked = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/follows/fol_fixture_bsc_protocol/track', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': key, 'if-match': '"rev-1"' },
      body: JSON.stringify({ confirmed: true }),
    }), { submitTracking: submit });
    assert.equal(tracked.status, 202);
    const body = (await tracked.json()).data;
    assert.equal(body.delivery, 'submitted');
    assert.equal(body.command.operation, 'tracking.create');
    assert.equal(body.command.payload.confirmed, true);
    assert.equal(body.command.subscription_id, null);
    assert.equal(body.command.expected_revision, null);
    assert.equal(body.command.tenant_id, 'ikun-main');
    assert.equal(body.command.project_id, 'prj_11111111-1111-4111-8111-111111111111');
    assert.equal(body.command.command_id, commandId('admin', TRACKING_CREATE_ROUTE, key));
    assert.equal(body.follow.status, 'tracked');
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.confirmed, true);
    assert.equal(String(calls[0]?.handle).toLowerCase(), 'bscvault');

    const replay = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/follows/fol_fixture_bsc_protocol/track', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': key, 'if-match': '"rev-1"' },
      body: JSON.stringify({ confirmed: true }),
    }), { submitTracking: submit });
    assert.equal(replay.status, 202);
    assert.equal(calls.length, 1);

    const pending = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/follows/fol_fixture_pending/track', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': '33333333-3333-4333-8333-333333333333', 'if-match': '"rev-1"' },
      body: '{}',
    }));
    assert.equal(pending.status, 422);

    const queued = await handleIntel(store, admin, new Request('http://127.0.0.1/api/v1/intel/follows/fol_fixture_pending/track', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'idempotency-key': '33333333-3333-4333-8333-333333333333', 'if-match': '"rev-1"' },
      body: JSON.stringify({ confirmed: true }),
    }));
    assert.equal(queued.status, 202);
    const queuedBody = (await queued.json()).data;
    assert.equal(queuedBody.delivery, 'queued');
    assert.equal(queuedBody.todo, '6551');
    assert.equal(queuedBody.command.operation, 'tracking.create');
    assert.equal(queuedBody.command.payload.confirmed, true);
    assert.equal(queuedBody.command.project_id, null);
    assert.equal(store.trackCommand('fol_fixture_pending')?.state, 'queued');

    const inferred = store.insertFollow({ x_handle: 'inferproto', seed_handle: 'solana', bio: 'DeFi protocol and oracle on Solana', recent_summary: 'bridge' });
    assert.equal(inferred.classification, 'project');
    assert.equal(inferred.chain, 'solana');
    assert.equal(store.trackCommand(inferred.follow_id), null);
    const meme = store.insertFollow({ x_handle: 'infercoin', seed_handle: 'solana', bio: 'memecoin protocol on Solana', recent_summary: '' });
    assert.equal(meme.account_type, 'token');
    assert.equal(meme.classification, 'noise');
    assert.equal(meme.promote_suggested, false);

    const tracking = readFileSync(new URL('../lib/tracking.ts', import.meta.url), 'utf8');
    assert.match(tracking, /submitTrackingCreate/);
    assert.match(tracking, /trackingCreateCommand\(/);
    const bridge = readFileSync(new URL('../lib/eco-intel/tracking-bridge.ts', import.meta.url), 'utf8');
    assert.match(bridge, /submitTrackingCreate/);
    assert.match(bridge, /TODO\(6551\)/);
    const route = readFileSync(new URL('../app/api/v1/intel/[[...path]]/route.ts', import.meta.url), 'utf8');
    assert.match(route, /submitIntelTracking/);
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
