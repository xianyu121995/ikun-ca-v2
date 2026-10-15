
  CREATE TABLE IF NOT EXISTS _schema_migrations (
    version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
  ) STRICT;
  CREATE TABLE IF NOT EXISTS _store_identity (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1), store_name TEXT NOT NULL
  ) STRICT;
