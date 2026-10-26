import { chmodSync, existsSync, lstatSync, mkdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { randomUUID } from 'node:crypto';
import { isAbsolute, join, parse, resolve } from 'node:path';
import { DEFAULT_SEEDS, FIXTURE_AT, STUB_FOLLOWS, STUB_TWEETS } from './fixtures';
import { IntelError, RULES_ANALYSIS, accountTypeOf, boundedText, classifyTweet, ecosystemOf, followDisposition, normalizeUrl, optionalTimestamp, requireHandle } from './rules';
import { INTEL_APPLICATION_ID, INTEL_FOUNDATION_SQL, INTEL_MIGRATION_CHECKSUM, INTEL_MIGRATION_SQL, INTEL_SCHEMA_VERSION } from './schema';
import type { AccountType, Ecosystem, FollowRecord, FollowStatus, IntelPage, QueueKind, QueueRecord, SeedRecord, SeedSource, TweetRecord } from './types';

type Row = Record<string, unknown>;

function rejectSymlinks(path: string) {
  let current = parse(path).root;
  for (const part of path.slice(current.length).split('/')) {
    if (!part) continue;
    current = join(current, part);
    if (existsSync(current) && lstatSync(current).isSymbolicLink()) throw new Error('INTEL_SYMLINK_REJECTED');
  }
}

function flag(value: unknown): boolean {
  return value === 1 || value === true;
}

function seedFrom(row: Row): SeedRecord {
  return {
    seed_id: String(row.seed_id),
    x_handle: String(row.x_handle),
    ecosystem: row.ecosystem as Ecosystem,
    role_label: String(row.role_label),
    notes: String(row.notes),
    enabled: flag(row.enabled),
    source: row.source as SeedSource,
    revision: Number(row.revision),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}

function tweetFrom(row: Row): TweetRecord {
  const topics = JSON.parse(String(row.topics_json)) as TweetRecord['topics'];
  const analysis = JSON.parse(String(row.analysis_json)) as TweetRecord['analysis'];
  return {
    tweet_id: String(row.tweet_id),
    seed_id: row.seed_id == null ? null : String(row.seed_id),
    x_handle: String(row.x_handle),
    text: String(row.text),
    url: String(row.url),
    occurred_at: row.occurred_at == null ? null : String(row.occurred_at),
    received_at: String(row.received_at),
    topics,
    push_to_feed: flag(row.push_to_feed),
    source: row.source as TweetRecord['source'],
    analysis_status: row.analysis_status as TweetRecord['analysis_status'],
    analysis,
    created_at: String(row.created_at),
  };
}

function followFrom(row: Row): FollowRecord {
  return {
    follow_id: String(row.follow_id),
    seed_id: row.seed_id == null ? null : String(row.seed_id),
    seed_handle: String(row.seed_handle),
    x_handle: String(row.x_handle),
    display_name: String(row.display_name),
    bio: String(row.bio),
    recent_summary: String(row.recent_summary),
    account_type: row.account_type as AccountType,
    promote_suggested: flag(row.promote_suggested),
    watch_tweets: flag(row.watch_tweets),
    promoted_seed_id: row.promoted_seed_id == null ? null : String(row.promoted_seed_id),
    notes: String(row.notes),
    status: row.status as FollowStatus,
    source: row.source as FollowRecord['source'],
    revision: Number(row.revision),
    occurred_at: row.occurred_at == null ? null : String(row.occurred_at),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}

function encodeCursor(stamp: string, id: string): string {
  return Buffer.from(`${stamp}\t${id}`).toString('base64url');
}

function decodeCursor(cursor: string | undefined): { stamp: string; id: string } | null {
  if (!cursor) return null;
  let text = '';
  try { text = Buffer.from(cursor, 'base64url').toString('utf8'); } catch { throw new IntelError(422, 'VALIDATION_ERROR', '游标无效'); }
  const split = text.split('\t');
  if (split.length !== 2 || !split[0] || !split[1]) throw new IntelError(422, 'VALIDATION_ERROR', '游标无效');
  return { stamp: split[0], id: split[1] };
}

function pageOf<T>(rows: T[], limit: number, stamp: (row: T) => string, id: (row: T) => string): IntelPage<T> {
  const more = rows.length > limit;
  const items = more ? rows.slice(0, limit) : rows;
  const last = items.at(-1);
  return { items, next_cursor: more && last ? encodeCursor(stamp(last), id(last)) : null };
}

export interface SeedInput {
  x_handle?: unknown;
  ecosystem?: unknown;
  role_label?: unknown;
  notes?: unknown;
  enabled?: unknown;
  source?: SeedSource;
  seed_id?: string;
  at?: string;
}

export interface SeedPatch {
  ecosystem?: unknown;
  role_label?: unknown;
  notes?: unknown;
  enabled?: unknown;
}

export interface TweetInput {
  x_handle?: unknown;
  text?: unknown;
  url?: unknown;
  occurred_at?: unknown;
  source?: TweetRecord['source'];
  tweet_id?: string;
  at?: string;
}

export interface FollowInput {
  x_handle?: unknown;
  seed_handle?: unknown;
  display_name?: unknown;
  bio?: unknown;
  recent_summary?: unknown;
  account_type?: unknown;
  notes?: unknown;
  occurred_at?: unknown;
  source?: FollowRecord['source'];
  follow_id?: string;
  at?: string;
}

export interface FollowPatch {
  notes?: unknown;
  account_type?: unknown;
  status?: unknown;
}

export interface IdempotencyHit {
  body_hash: string;
  status: number;
  kind: 'data' | 'error';
  body: unknown;
}

export function intelDbPath(dataRoot = process.env.DATA_ROOT): string {
  if (!dataRoot || !isAbsolute(dataRoot)) throw new Error('INTEL_DATA_ROOT_REQUIRED');
  return join(resolve(dataRoot), 'intel', 'intel.db');
}

export class IntelStore {
  constructor(readonly db: DatabaseSync, readonly path: string) {}

  close() {
    try { if (this.db.isTransaction) this.db.exec('ROLLBACK'); this.db.close(); } catch { /* already closed */ }
  }

  transaction<T>(fn: () => T): T {
    if (this.db.isTransaction) return fn();
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const value = fn();
      this.db.exec('COMMIT');
      return value;
    } catch (error) {
      if (this.db.isTransaction) this.db.exec('ROLLBACK');
      throw error;
    }
  }

  recall(actorId: string, route: string, key: string): IdempotencyHit | null {
    const row = this.db.prepare('SELECT body_hash, status, response_json FROM intel_idempotency WHERE actor_id=? AND route=? AND idempotency_key=?').get(actorId, route, key) as Row | undefined;
    if (!row) return null;
    const parsed = JSON.parse(String(row.response_json)) as { kind: 'data' | 'error'; body: unknown };
    return { body_hash: String(row.body_hash), status: Number(row.status), kind: parsed.kind, body: parsed.body };
  }

  remember(actorId: string, route: string, key: string, bodyHash: string, status: number, kind: 'data' | 'error', body: unknown) {
    this.db.prepare('INSERT INTO intel_idempotency(actor_id, route, idempotency_key, body_hash, status, response_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)').run(
      actorId, route, key, bodyHash, status, JSON.stringify({ kind, body }), new Date().toISOString(),
    );
  }

  listSeeds(query: string, limit: number, cursor?: string): IntelPage<SeedRecord> {
    const mark = decodeCursor(cursor);
    const rows = this.db.prepare(`SELECT * FROM intel_seeds
      WHERE (? = '' OR instr(lower(x_handle), lower(?)) > 0 OR instr(lower(role_label), lower(?)) > 0 OR instr(lower(notes), lower(?)) > 0)
      AND (? = '' OR updated_at < ? OR (updated_at = ? AND seed_id < ?))
      ORDER BY updated_at DESC, seed_id DESC LIMIT ?`).all(query, query, query, query, mark ? '1' : '', mark?.stamp ?? '', mark?.stamp ?? '', mark?.id ?? '', limit + 1) as Row[];
    return pageOf(rows.map(seedFrom), limit, row => row.updated_at, row => row.seed_id);
  }

  getSeed(id: string): SeedRecord | null {
    const row = this.db.prepare('SELECT * FROM intel_seeds WHERE seed_id=?').get(id) as Row | undefined;
    return row ? seedFrom(row) : null;
  }

  findSeedByHandle(handle: string): SeedRecord | null {
    const row = this.db.prepare('SELECT * FROM intel_seeds WHERE x_handle=? COLLATE NOCASE').get(handle) as Row | undefined;
    return row ? seedFrom(row) : null;
  }

  insertSeed(input: SeedInput): SeedRecord {
    return this.transaction(() => this.insertSeedRow(input));
  }

  updateSeed(id: string, revision: number, patch: SeedPatch): SeedRecord {
    return this.transaction(() => {
      const current = this.requireSeed(id);
      if (current.revision !== revision) throw new IntelError(409, 'VERSION_CONFLICT', '种子已被他人更新，请刷新后重试');
      const ecosystem = patch.ecosystem === undefined ? current.ecosystem : ecosystemOf(patch.ecosystem);
      const role = patch.role_label === undefined ? current.role_label : boundedText(patch.role_label, 40, '角色');
      const notes = patch.notes === undefined ? current.notes : boundedText(patch.notes, 2000, '备注');
      const enabled = patch.enabled === undefined ? current.enabled : requireBoolean(patch.enabled, '启用状态');
      const now = new Date().toISOString();
      const result = this.db.prepare(`UPDATE intel_seeds SET ecosystem=?, role_label=?, notes=?, enabled=?, revision=revision+1, updated_at=? WHERE seed_id=? AND revision=?`).run(
        ecosystem, role, notes, enabled ? 1 : 0, now, id, revision,
      );
      if (result.changes !== 1) throw new IntelError(409, 'VERSION_CONFLICT', '种子已被他人更新，请刷新后重试');
      return this.requireSeed(id);
    });
  }

  deleteSeed(id: string, revision: number): void {
    this.transaction(() => {
      const result = this.db.prepare('DELETE FROM intel_seeds WHERE seed_id=? AND revision=?').run(id, revision);
      if (result.changes === 1) return;
      if (!this.getSeed(id)) throw new IntelError(404, 'NOT_FOUND', '种子不存在');
      throw new IntelError(409, 'VERSION_CONFLICT', '种子已被他人更新，请刷新后重试');
    });
  }

  listTweets(query: string, limit: number, cursor?: string): IntelPage<TweetRecord> {
    const mark = decodeCursor(cursor);
    const rows = this.db.prepare(`SELECT * FROM intel_tweets
      WHERE (? = '' OR instr(lower(x_handle), lower(?)) > 0 OR instr(lower(text), lower(?)) > 0)
      AND (? = '' OR received_at < ? OR (received_at = ? AND tweet_id < ?))
      ORDER BY received_at DESC, tweet_id DESC LIMIT ?`).all(query, query, query, mark ? '1' : '', mark?.stamp ?? '', mark?.stamp ?? '', mark?.id ?? '', limit + 1) as Row[];
    return pageOf(rows.map(tweetFrom), limit, row => row.received_at, row => row.tweet_id);
  }

  insertTweet(input: TweetInput): TweetRecord {
    return this.transaction(() => this.insertTweetRow(input));
  }

  listFollows(query: string, status: string, limit: number, cursor?: string): IntelPage<FollowRecord> {
    if (status && !['open', 'promoted', 'dismissed'].includes(status)) throw new IntelError(422, 'VALIDATION_ERROR', '状态筛选无效');
    const mark = decodeCursor(cursor);
    const rows = this.db.prepare(`SELECT * FROM intel_follows
      WHERE (? = '' OR status = ?)
      AND (? = '' OR instr(lower(x_handle), lower(?)) > 0 OR instr(lower(seed_handle), lower(?)) > 0 OR instr(lower(notes), lower(?)) > 0 OR instr(lower(bio), lower(?)) > 0)
      AND (? = '' OR updated_at < ? OR (updated_at = ? AND follow_id < ?))
      ORDER BY updated_at DESC, follow_id DESC LIMIT ?`).all(
      status, status, query, query, query, query, query, mark ? '1' : '', mark?.stamp ?? '', mark?.stamp ?? '', mark?.id ?? '', limit + 1,
    ) as Row[];
    return pageOf(rows.map(followFrom), limit, row => row.updated_at, row => row.follow_id);
  }

  getFollow(id: string): FollowRecord | null {
    const row = this.db.prepare('SELECT * FROM intel_follows WHERE follow_id=?').get(id) as Row | undefined;
    return row ? followFrom(row) : null;
  }

  insertFollow(input: FollowInput): FollowRecord {
    return this.transaction(() => this.insertFollowRow(input));
  }

  updateFollow(id: string, revision: number, patch: FollowPatch): FollowRecord {
    return this.transaction(() => {
      const current = this.requireFollow(id);
      if (current.revision !== revision) throw new IntelError(409, 'VERSION_CONFLICT', '关注记录已被他人更新，请刷新后重试');
      if (current.status === 'promoted' && patch.status !== undefined && patch.status !== 'promoted') {
        throw new IntelError(409, 'CONFLICT', '已升为种子的记录不能改回其他状态');
      }
      const notes = patch.notes === undefined ? current.notes : boundedText(patch.notes, 2000, '备注');
      const accountType = patch.account_type === undefined ? current.account_type : accountTypeOf(patch.account_type);
      let status = current.status;
      if (patch.status !== undefined) {
        if (patch.status !== 'open' && patch.status !== 'dismissed') throw new IntelError(422, 'VALIDATION_ERROR', '状态只能改为待处理或忽略');
        status = patch.status;
      }
      const disposition = followDisposition(accountType);
      const now = new Date().toISOString();
      const result = this.db.prepare(`UPDATE intel_follows SET notes=?, account_type=?, promote_suggested=?, watch_tweets=?, status=?, revision=revision+1, updated_at=? WHERE follow_id=? AND revision=?`).run(
        notes, accountType, disposition.promote_suggested ? 1 : 0, disposition.watch_tweets ? 1 : 0, status, now, id, revision,
      );
      if (result.changes !== 1) throw new IntelError(409, 'VERSION_CONFLICT', '关注记录已被他人更新，请刷新后重试');
      return this.requireFollow(id);
    });
  }

  deleteFollow(id: string, revision: number): void {
    this.transaction(() => {
      const current = this.getFollow(id);
      if (!current) throw new IntelError(404, 'NOT_FOUND', '关注记录不存在');
      if (current.status === 'promoted') throw new IntelError(409, 'CONFLICT', '已升为种子的记录请在种子列表中管理');
      const result = this.db.prepare('DELETE FROM intel_follows WHERE follow_id=? AND revision=?').run(id, revision);
      if (result.changes !== 1) throw new IntelError(409, 'VERSION_CONFLICT', '关注记录已被他人更新，请刷新后重试');
    });
  }

  promoteFollow(id: string, revision: number, ecosystemRaw: unknown, roleRaw: unknown): { follow: FollowRecord; seed: SeedRecord } {
    return this.transaction(() => {
      const current = this.requireFollow(id);
      if (current.revision !== revision) throw new IntelError(409, 'VERSION_CONFLICT', '关注记录已被他人更新，请刷新后重试');
      if (current.status === 'dismissed') throw new IntelError(409, 'CONFLICT', '已忽略的关注不能升为种子');
      if (current.status === 'promoted' && current.promoted_seed_id) {
        const linked = this.getSeed(current.promoted_seed_id);
        if (linked) return { follow: current, seed: linked };
      }
      const parent = current.seed_handle ? this.findSeedByHandle(current.seed_handle) : null;
      const ecosystem = ecosystemRaw === undefined || ecosystemRaw === '' ? (parent?.ecosystem ?? 'other') : ecosystemOf(ecosystemRaw);
      const role = roleRaw === undefined || roleRaw === '' ? (labelFor(current.account_type)) : boundedText(roleRaw, 40, '角色');
      let seed = this.findSeedByHandle(current.x_handle);
      if (!seed) {
        seed = this.insertSeedRow({
          x_handle: current.x_handle,
          ecosystem,
          role_label: role,
          notes: current.notes,
          enabled: true,
          source: 'promoted',
        });
      }
      const now = new Date().toISOString();
      const result = this.db.prepare(`UPDATE intel_follows SET status='promoted', promoted_seed_id=?, revision=revision+1, updated_at=? WHERE follow_id=? AND revision=?`).run(
        seed.seed_id, now, id, revision,
      );
      if (result.changes !== 1) throw new IntelError(409, 'VERSION_CONFLICT', '关注记录已被他人更新，请刷新后重试');
      return { follow: this.requireFollow(id), seed };
    });
  }

  enqueue(kind: QueueKind, payload: Record<string, unknown>): QueueRecord {
    return this.transaction(() => {
      const now = new Date().toISOString();
      const queueId = `q_${randomUUID()}`;
      this.db.prepare(`INSERT INTO intel_ingest_queue(queue_id, kind, payload_json, status, attempts, last_error, created_at, updated_at) VALUES (?, ?, ?, 'pending', 0, '', ?, ?)`).run(
        queueId, kind, JSON.stringify(payload), now, now,
      );
      return { queue_id: queueId, kind, status: 'pending', attempts: 0, created_at: now };
    });
  }

  private requireSeed(id: string): SeedRecord {
    const row = this.getSeed(id);
    if (!row) throw new IntelError(404, 'NOT_FOUND', '种子不存在');
    return row;
  }

  private requireFollow(id: string): FollowRecord {
    const row = this.getFollow(id);
    if (!row) throw new IntelError(404, 'NOT_FOUND', '关注记录不存在');
    return row;
  }

  private insertSeedRow(input: SeedInput): SeedRecord {
    const handle = requireHandle(input.x_handle);
    const ecosystem = ecosystemOf(input.ecosystem);
    const role = boundedText(input.role_label, 40, '角色');
    const notes = boundedText(input.notes, 2000, '备注');
    const enabled = input.enabled === undefined ? true : requireBoolean(input.enabled, '启用状态');
    const source = input.source ?? 'manual';
    const now = input.at ?? new Date().toISOString();
    const seedId = input.seed_id ?? `seed_${randomUUID()}`;
    try {
      this.db.prepare(`INSERT INTO intel_seeds(seed_id, x_handle, ecosystem, role_label, notes, enabled, source, revision, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)`).run(
        seedId, handle, ecosystem, role, notes, enabled ? 1 : 0, source, now, now,
      );
    } catch (error) {
      if (error instanceof Error && /UNIQUE/i.test(error.message)) throw new IntelError(409, 'CONFLICT', '种子账号已存在');
      throw error;
    }
    return this.requireSeed(seedId);
  }

  private insertTweetRow(input: TweetInput): TweetRecord {
    const handle = requireHandle(input.x_handle);
    const seed = this.findSeedByHandle(handle);
    if (!seed) throw new IntelError(422, 'VALIDATION_ERROR', '推文账号必须已是种子');
    const text = boundedText(input.text, 2000, '推文', true);
    const url = normalizeUrl(input.url);
    const occurred = optionalTimestamp(input.occurred_at);
    const classified = classifyTweet(text);
    const now = input.at ?? new Date().toISOString();
    const tweetId = input.tweet_id ?? `tw_${randomUUID()}`;
    const source = input.source ?? 'manual';
    this.db.prepare(`INSERT INTO intel_tweets(tweet_id, seed_id, x_handle, text, url, occurred_at, received_at, topics_json, push_to_feed, source, analysis_status, analysis_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'done', ?, ?)`).run(
      tweetId, seed.seed_id, seed.x_handle, text, url, occurred, now, JSON.stringify(classified.topics), classified.push_to_feed ? 1 : 0, source, JSON.stringify(RULES_ANALYSIS), now,
    );
    const row = this.db.prepare('SELECT * FROM intel_tweets WHERE tweet_id=?').get(tweetId) as Row;
    return tweetFrom(row);
  }

  private insertFollowRow(input: FollowInput): FollowRecord {
    const handle = requireHandle(input.x_handle);
    const seedHandleRaw = input.seed_handle === undefined || input.seed_handle === '' ? '' : requireHandle(input.seed_handle, '种子用户名');
    const seed = seedHandleRaw ? this.findSeedByHandle(seedHandleRaw) : null;
    if (seedHandleRaw && !seed) throw new IntelError(422, 'VALIDATION_ERROR', '来源种子不存在');
    const accountType = input.account_type === undefined || input.account_type === '' ? 'unclassified' : accountTypeOf(input.account_type);
    const disposition = followDisposition(accountType);
    const now = input.at ?? new Date().toISOString();
    const followId = input.follow_id ?? `fol_${randomUUID()}`;
    this.db.prepare(`INSERT INTO intel_follows(follow_id, seed_id, seed_handle, x_handle, display_name, bio, recent_summary, account_type, promote_suggested, watch_tweets, promoted_seed_id, notes, status, source, revision, occurred_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'open', ?, 1, ?, ?, ?)`).run(
      followId,
      seed?.seed_id ?? null,
      seed?.x_handle ?? seedHandleRaw,
      handle,
      boundedText(input.display_name, 80, '显示名'),
      boundedText(input.bio, 1000, '简介'),
      boundedText(input.recent_summary, 2000, '近期摘要'),
      accountType,
      disposition.promote_suggested ? 1 : 0,
      disposition.watch_tweets ? 1 : 0,
      boundedText(input.notes, 2000, '备注'),
      input.source ?? 'manual',
      optionalTimestamp(input.occurred_at),
      now,
      now,
    );
    return this.requireFollow(followId);
  }
}

function requireBoolean(raw: unknown, field: string): boolean {
  if (typeof raw !== 'boolean') throw new IntelError(422, 'VALIDATION_ERROR', `${field}须为布尔值`);
  return raw;
}

function labelFor(accountType: AccountType): string {
  if (accountType === 'protocol') return '新协议';
  if (accountType === 'launchpad') return '发射台';
  if (accountType === 'hackathon') return '黑客松项目';
  if (accountType === 'official') return '官方';
  if (accountType === 'founder') return '创始人';
  if (accountType === 'token') return '新币';
  return '待定';
}

function migrate(db: DatabaseSync) {
  db.exec('BEGIN IMMEDIATE');
  try {
    const marker = db.prepare('PRAGMA application_id').get() as { application_id?: number } | undefined;
    const appId = Number(marker?.application_id ?? 0);
    if (appId === 0) {
      db.exec(`PRAGMA application_id=${INTEL_APPLICATION_ID};${INTEL_FOUNDATION_SQL}`);
      db.prepare('INSERT INTO _store_identity(singleton, store_name) VALUES (1, ?)').run('intel');
      db.prepare("INSERT INTO _schema_migrations(version, name, applied_at) VALUES (1, 'foundation', ?)").run(new Date().toISOString());
    } else if (appId !== INTEL_APPLICATION_ID) {
      throw new Error('INTEL_FOREIGN_DATABASE_REJECTED');
    }
    const identity = db.prepare('SELECT store_name FROM _store_identity WHERE singleton=1').get() as { store_name?: string } | undefined;
    if (identity?.store_name !== 'intel') throw new Error('INTEL_STORE_MISMATCH');
    db.exec('CREATE TABLE IF NOT EXISTS _migration_checksums (version INTEGER PRIMARY KEY, sha256 TEXT NOT NULL) STRICT;');
    const versionRow = db.prepare('SELECT MAX(version) AS version FROM _schema_migrations').get() as { version?: number } | undefined;
    const version = Number(versionRow?.version ?? 0);
    if (version === 1) {
      db.exec(INTEL_MIGRATION_SQL);
      db.prepare("INSERT INTO _schema_migrations(version, name, applied_at) VALUES (2, 'eco_intel_v1', ?)").run(new Date().toISOString());
      db.prepare('INSERT INTO _migration_checksums(version, sha256) VALUES (2, ?)').run(INTEL_MIGRATION_CHECKSUM);
      db.exec(`PRAGMA user_version=${INTEL_SCHEMA_VERSION};`);
      applyFixtures(db);
    } else if (version === INTEL_SCHEMA_VERSION) {
      const sum = db.prepare('SELECT sha256 FROM _migration_checksums WHERE version=2').get() as { sha256?: string } | undefined;
      if (sum?.sha256 !== INTEL_MIGRATION_CHECKSUM) throw new Error('INTEL_MIGRATION_CHECKSUM_MISMATCH');
      const userVersion = Number((db.prepare('PRAGMA user_version').get() as { user_version?: number } | undefined)?.user_version ?? 0);
      if (userVersion !== INTEL_SCHEMA_VERSION) throw new Error('INTEL_UNSUPPORTED_VERSION');
    } else {
      throw new Error('INTEL_UNSUPPORTED_VERSION');
    }
    db.exec('COMMIT');
  } catch (error) {
    if (db.isTransaction) db.exec('ROLLBACK');
    throw error;
  }
}

function applyFixtures(db: DatabaseSync) {
  const store = new IntelStore(db, '');
  for (const seed of DEFAULT_SEEDS) {
    store.insertSeed({
      seed_id: `seed_fixture_${seed.handle.toLowerCase()}`,
      x_handle: seed.handle,
      ecosystem: seed.ecosystem,
      role_label: seed.role,
      notes: '本地夹具，未连接 6551。',
      enabled: true,
      source: 'fixture',
      at: FIXTURE_AT,
    });
  }
  for (const tweet of STUB_TWEETS) {
    store.insertTweet({
      tweet_id: tweet.id,
      x_handle: tweet.handle,
      text: tweet.text,
      url: tweet.url,
      occurred_at: FIXTURE_AT,
      source: 'stub',
      at: FIXTURE_AT,
    });
  }
  for (const follow of STUB_FOLLOWS) {
    store.insertFollow({
      follow_id: follow.id,
      x_handle: follow.handle,
      seed_handle: follow.seed,
      display_name: follow.name,
      bio: follow.bio,
      recent_summary: follow.summary,
      account_type: follow.type,
      notes: '本地夹具，未连接 6551。',
      occurred_at: FIXTURE_AT,
      source: 'stub',
      at: FIXTURE_AT,
    });
  }
  db.prepare('INSERT INTO intel_state(key, value) VALUES (?, ?)').run('fixtures_v1', 'applied');
}

/** Explicit open+migrate. Safe to call again; it does not reinsert fixtures. */
export function openIntelStore(dbPath: string): IntelStore {
  if (!isAbsolute(dbPath)) throw new Error('INTEL_DATA_ROOT_REQUIRED');
  const directory = parse(dbPath).dir;
  rejectSymlinks(directory);
  rejectSymlinks(dbPath);
  for (const suffix of ['-wal', '-shm']) rejectSymlinks(`${dbPath}${suffix}`);
  if (!existsSync(directory)) mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (existsSync(dbPath) && lstatSync(dbPath).nlink !== 1) throw new Error('INTEL_HARDLINK_REJECTED');
  const db = new DatabaseSync(dbPath, { timeout: 5000 });
  try {
    db.exec('PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000; PRAGMA synchronous=FULL;');
    db.exec('PRAGMA journal_mode=WAL;');
    migrate(db);
    chmodSync(directory, 0o700);
    chmodSync(dbPath, 0o600);
    return new IntelStore(db, dbPath);
  } catch (error) {
    try { if (db.isTransaction) db.exec('ROLLBACK'); db.close(); } catch { /* already closed */ }
    throw error;
  }
}

const globalState = globalThis as typeof globalThis & { ikunIntelStore?: IntelStore };

export function intelStore(): IntelStore {
  if (!globalState.ikunIntelStore) globalState.ikunIntelStore = openIntelStore(intelDbPath());
  return globalState.ikunIntelStore;
}
