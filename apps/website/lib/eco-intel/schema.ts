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
export const INTEL_SCHEMA_VERSION = 2;
