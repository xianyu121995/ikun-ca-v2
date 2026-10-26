import { createHash } from 'node:crypto';

/**
 * Business migration for the independent intel.db.
 * Byte-for-byte with schemas/intel/001_eco_intel.sql (enforced by eco-intel tests).
 * Inlined so the website server does not depend on process.cwd().
 */
export const INTEL_MIGRATION_SQL = `-- eco-intel v1. Independent of hunter.db, tracking.db, projects.db and auth.db.
-- TODO(6551): a later worker should drain intel_ingest_queue from 6551 WSS events.
-- This file never attaches another database and never calls a provider.

CREATE TABLE intel_seeds (
  seed_id TEXT PRIMARY KEY,
  x_handle TEXT NOT NULL COLLATE NOCASE UNIQUE,
  ecosystem TEXT NOT NULL,
  role_label TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  source TEXT NOT NULL DEFAULT 'manual',
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (enabled IN (0, 1)),
  CHECK (source IN ('fixture', 'manual', 'promoted')),
  CHECK (ecosystem IN ('bsc', 'solana', 'eth', 'base', 'robinhood', 'other')),
  CHECK (length(x_handle) BETWEEN 1 AND 15)
) STRICT;
CREATE INDEX intel_seeds_updated ON intel_seeds(updated_at, seed_id);

CREATE TABLE intel_tweets (
  tweet_id TEXT PRIMARY KEY,
  seed_id TEXT REFERENCES intel_seeds(seed_id) ON DELETE SET NULL,
  x_handle TEXT NOT NULL,
  text TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  occurred_at TEXT,
  received_at TEXT NOT NULL,
  topics_json TEXT NOT NULL DEFAULT '[]',
  push_to_feed INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'manual',
  analysis_status TEXT NOT NULL DEFAULT 'pending',
  analysis_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  CHECK (push_to_feed IN (0, 1)),
  CHECK (source IN ('stub', 'manual', 'wss', 'rest')),
  CHECK (analysis_status IN ('pending', 'skipped', 'done')),
  CHECK (length(text) BETWEEN 1 AND 2000)
) STRICT;
CREATE INDEX intel_tweets_received ON intel_tweets(received_at, tweet_id);
CREATE INDEX intel_tweets_handle ON intel_tweets(x_handle);

CREATE TABLE intel_follows (
  follow_id TEXT PRIMARY KEY,
  seed_id TEXT REFERENCES intel_seeds(seed_id) ON DELETE SET NULL,
  seed_handle TEXT NOT NULL DEFAULT '',
  x_handle TEXT NOT NULL COLLATE NOCASE,
  display_name TEXT NOT NULL DEFAULT '',
  bio TEXT NOT NULL DEFAULT '',
  recent_summary TEXT NOT NULL DEFAULT '',
  account_type TEXT NOT NULL DEFAULT 'unclassified',
  promote_suggested INTEGER NOT NULL DEFAULT 0,
  watch_tweets INTEGER NOT NULL DEFAULT 0,
  promoted_seed_id TEXT,
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  source TEXT NOT NULL DEFAULT 'manual',
  revision INTEGER NOT NULL DEFAULT 1,
  occurred_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (promote_suggested IN (0, 1)),
  CHECK (watch_tweets IN (0, 1)),
  CHECK (account_type IN ('official', 'launchpad', 'hackathon', 'protocol', 'token', 'founder', 'unrelated', 'unclassified')),
  CHECK (status IN ('open', 'promoted', 'dismissed')),
  CHECK (source IN ('stub', 'manual', 'wss')),
  CHECK (length(x_handle) BETWEEN 1 AND 15)
) STRICT;
CREATE INDEX intel_follows_updated ON intel_follows(updated_at, follow_id);
CREATE INDEX intel_follows_handle ON intel_follows(x_handle);

CREATE TABLE intel_ingest_queue (
  queue_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (kind IN ('wss_follow', 'wss_tweet', 'ai_analyze')),
  CHECK (status IN ('pending', 'processing', 'done', 'failed', 'skipped'))
) STRICT;
CREATE INDEX intel_queue_status ON intel_ingest_queue(status, created_at);

CREATE TABLE intel_idempotency (
  actor_id TEXT NOT NULL,
  route TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  body_hash TEXT NOT NULL,
  status INTEGER NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (actor_id, route, idempotency_key)
) STRICT;

CREATE TABLE intel_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
) STRICT;
`;

export const INTEL_MIGRATION_CHECKSUM = createHash('sha256').update(INTEL_MIGRATION_SQL).digest('hex');

/** Matches the four-store foundation tables without registering a fifth StoreName. */
export const INTEL_FOUNDATION_SQL = `
CREATE TABLE IF NOT EXISTS _schema_migrations (
  version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS _store_identity (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1), store_name TEXT NOT NULL
) STRICT;
`;

/** Distinct from hunter 0x494B0201, tracking 0x494B0202, projects 0x494B0203, auth 0x494B0204. */
export const INTEL_APPLICATION_ID = 0x494b0210;
export const INTEL_SCHEMA_VERSION = 3;

/**
 * Adds chain, classification, and the tracking.create outbox.
 * Applied after 001. Does not rewrite the v2 checksum.
 * TODO(6551): a queued command is delivered by the existing projects/tracking path, not a new monitor.
 */
export const INTEL_PROJECTS_SQL = `-- eco-intel projects. Chain filter, classification, and tracking.create outbox.
-- Independent of hunter.db, tracking.db, projects.db and auth.db.
-- TODO(6551): queued commands are handed to the existing tracking.create path.
-- This migration never attaches another database and never calls a provider.

CREATE TABLE intel_follows_v3 (
  follow_id TEXT PRIMARY KEY,
  seed_id TEXT REFERENCES intel_seeds(seed_id) ON DELETE SET NULL,
  seed_handle TEXT NOT NULL DEFAULT '',
  x_handle TEXT NOT NULL COLLATE NOCASE,
  display_name TEXT NOT NULL DEFAULT '',
  bio TEXT NOT NULL DEFAULT '',
  recent_summary TEXT NOT NULL DEFAULT '',
  account_type TEXT NOT NULL DEFAULT 'unclassified',
  chain TEXT NOT NULL DEFAULT '',
  classification TEXT NOT NULL DEFAULT 'pending',
  promote_suggested INTEGER NOT NULL DEFAULT 0,
  watch_tweets INTEGER NOT NULL DEFAULT 0,
  promoted_seed_id TEXT,
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  track_state TEXT NOT NULL DEFAULT 'none',
  source TEXT NOT NULL DEFAULT 'manual',
  revision INTEGER NOT NULL DEFAULT 1,
  occurred_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (promote_suggested IN (0, 1)),
  CHECK (watch_tweets IN (0, 1)),
  CHECK (account_type IN ('official', 'launchpad', 'hackathon', 'protocol', 'token', 'founder', 'unrelated', 'unclassified', 'kol', 'media', 'exchange', 'personal', 'airdrop', 'brand')),
  CHECK (chain IN ('', 'bsc', 'solana', 'eth', 'base', 'robinhood')),
  CHECK (classification IN ('project', 'noise', 'pending')),
  CHECK (status IN ('open', 'promoted', 'dismissed', 'pending', 'tracked')),
  CHECK (track_state IN ('none', 'queued', 'submitted')),
  CHECK (source IN ('stub', 'manual', 'wss')),
  CHECK (length(x_handle) BETWEEN 1 AND 15)
) STRICT;

INSERT INTO intel_follows_v3(
  follow_id, seed_id, seed_handle, x_handle, display_name, bio, recent_summary, account_type,
  chain, classification, promote_suggested, watch_tweets, promoted_seed_id, notes, status, track_state,
  source, revision, occurred_at, created_at, updated_at
)
SELECT
  follow_id, seed_id, seed_handle, x_handle, display_name, bio, recent_summary, account_type,
  '',
  CASE
    WHEN account_type IN ('token', 'founder', 'unrelated', 'official') THEN 'noise'
    ELSE 'pending'
  END,
  0,
  0,
  promoted_seed_id, notes,
  CASE
    WHEN status IN ('promoted', 'dismissed') THEN status
    WHEN account_type IN ('token', 'founder', 'unrelated', 'official') THEN 'open'
    ELSE 'pending'
  END,
  'none',
  source, revision, occurred_at, created_at, updated_at
FROM intel_follows;

DROP TABLE intel_follows;
ALTER TABLE intel_follows_v3 RENAME TO intel_follows;
CREATE INDEX intel_follows_updated ON intel_follows(updated_at, follow_id);
CREATE INDEX intel_follows_handle ON intel_follows(x_handle);
CREATE INDEX intel_follows_chain ON intel_follows(classification, chain, updated_at, follow_id);

CREATE TABLE intel_track_outbox (
  command_id TEXT PRIMARY KEY,
  follow_id TEXT NOT NULL UNIQUE,
  idempotency_key TEXT NOT NULL,
  command_json TEXT NOT NULL,
  state TEXT NOT NULL,
  remote_state TEXT NOT NULL DEFAULT '',
  last_error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (state IN ('queued', 'submitted', 'rejected')),
  CHECK (length(command_json) > 2)
) STRICT;
CREATE INDEX intel_track_state ON intel_track_outbox(state, updated_at);
`;

export const INTEL_PROJECTS_CHECKSUM = createHash('sha256').update(INTEL_PROJECTS_SQL).digest('hex');
