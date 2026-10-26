-- eco-intel projects. Chain filter, classification, and tracking.create outbox.
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
