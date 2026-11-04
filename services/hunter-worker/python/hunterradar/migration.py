"""One explicit Hunter migration owner. Serve/readiness never initialize storage."""
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import uuid
from datetime import datetime, timezone

APP_ID=0x494B0201
SQL_ROOT=Path(__file__).resolve().parents[4]/'schemas/hunter'
FILES={1:'001_foundation.sql',2:'002_hunterradar.sql',3:'003_b4_protocol.sql',4:'004_research_retention.sql',5:'005_legacy_takeover.sql'}
NAMES={1:'foundation',2:'hunterradar_business',3:'hunter_b4_protocol',4:'hunter_research_retention',5:'hunter_legacy_takeover'}
LATEST_VERSION=5
READABLE_VERSIONS=(4,5)
TAKEOVER_TABLES=('hunter_takeover_runs','hunter_takeover_rows','hunter_takeover_conflicts',
                 'hunter_takeover_baselines','hunter_takeover_seen_times','hunter_takeover_project_refs')

def location(value, *, require_exists=False):
    path=Path(value).absolute()
    if path.name!='hunter.db':raise ValueError('database_must_be_named_hunter.db')
    files=(path,Path(str(path)+'-wal'),Path(str(path)+'-shm'));observed={}
    for part in (*path.parents,*files):
        try:entry=part.lstat()
        except FileNotFoundError:
            if require_exists and part==path:raise ValueError('hunter_migration_required') from None
            continue # SQLite may remove WAL/SHM normally between connections.
        # SQLite can unlink a WAL/SHM between pathname lookup and lstat.
        # A zero-link sidecar is already detached; main DB and hardlinks still fail closed.
        if part in files[1:] and stat.S_ISREG(entry.st_mode) and entry.st_nlink == 0:
            continue
        observed[part]=entry
        if stat.S_ISLNK(entry.st_mode):raise ValueError('symlinked_database_path_forbidden')
        if not stat.S_ISDIR(entry.st_mode) and (not stat.S_ISREG(entry.st_mode) or entry.st_nlink!=1):raise ValueError('database_must_be_private_regular_file')
        if part in files and not stat.S_ISREG(entry.st_mode):raise ValueError('database_must_be_private_regular_file')
        if require_exists and part in files and entry.st_mode&0o077:raise ValueError('unsafe_hunter_permissions')
    if require_exists:
        if path not in observed:raise ValueError('hunter_migration_required')
        if (observed[path].st_mode|observed[path.parent].st_mode)&0o077:raise ValueError('unsafe_hunter_permissions')
    return path

def checksums():return {version:hashlib.sha256((SQL_ROOT/file).read_bytes()).hexdigest() for version,file in FILES.items()}

def statements(db,sql):
    pending=''
    for line in sql.splitlines(True):
        pending+=line
        if sqlite3.complete_statement(pending):db.execute(pending);pending=''
    if pending.strip():raise ValueError('incomplete_migration')

def metadata(db, *, complete=True):
    if db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID:raise ValueError('foreign_database_refused')
    columns={row[1] for row in db.execute('PRAGMA table_info(_schema_migrations)')}
    if not {'version','name','applied_at'}<=columns or columns-{'version','name','applied_at','checksum'}:raise ValueError('unsupported_migration_metadata')
    identity=db.execute('SELECT store_name FROM _store_identity WHERE singleton=1').fetchone()
    if not identity or identity[0]!='hunter':raise ValueError('store_owner_mismatch')
    rows=db.execute('SELECT version,name FROM _schema_migrations ORDER BY version').fetchall()
    versions=[row[0] for row in rows]
    if not versions or max(versions)>LATEST_VERSION or versions!=list(range(1,len(versions)+1)) or any(name!=NAMES[version] for version,name in rows):raise ValueError('unsupported_schema_version')
    user_version=db.execute('PRAGMA user_version').fetchone()[0]
    if user_version>max(versions) or (max(versions)>=2 and user_version!=max(versions)):raise ValueError('unsupported_schema_version')
    tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'hunter_takeover_schema' in tables:raise ValueError('unreviewed_parallel_takeover_schema')
    expected=checksums()
    if 'checksum' in columns:
        for version,checksum in db.execute('SELECT version,checksum FROM _schema_migrations'):
            if checksum!=expected[version]:raise ValueError('hunter_migration_checksum_mismatch')
    if '_migration_checksums' in tables:
        actual=dict(db.execute('SELECT version,sha256 FROM _migration_checksums'))
        if set(actual)!=set(versions) or any(actual[v]!=expected[v] for v in versions):raise ValueError('hunter_migration_checksum_mismatch')
    elif complete:raise ValueError('hunter_checksum_migration_required')
    if 2 in versions:
        old=dict(db.execute('SELECT version,checksum FROM _hunter_migrations'))
        if old!={2:expected[2]}:raise ValueError('hunter_migration_checksum_mismatch')
    if complete and max(versions) not in READABLE_VERSIONS:raise ValueError('hunter_migration_required')
    if max(versions)>=5 and not set(TAKEOVER_TABLES)<=tables:raise ValueError('hunter_migration_required')
    return versions,columns

def ensure_rating_reason(value) -> bool:
    """Add discoveries.rating_reason and rating_source when missing.

    Idempotent and outside the checksummed 001–005 chain, so a database already
    at version 5 picks the columns up on hunter startup without a version bump.
    rating_source is 'ai' or 'human'. A rated row is marked ai only when
    rating_reason is set, because only apply_rating writes that column.
    Every other rated row defaults to human. Unrated rows stay unset so a
    later prefill can still run. Returns True when this call added a column.
    """
    path = location(value, require_exists=True)
    db = sqlite3.connect(path, timeout=5)
    added = False
    try:
        db.execute('PRAGMA busy_timeout=5000')
        db.execute('BEGIN IMMEDIATE')
        columns = {row[1] for row in db.execute('PRAGMA table_info(discoveries)')}
        if 'rating_reason' not in columns:
            db.execute('ALTER TABLE discoveries ADD COLUMN rating_reason TEXT')
            added = True
        if 'rating_source' not in columns:
            db.execute('ALTER TABLE discoveries ADD COLUMN rating_source TEXT')
            added = True
        db.execute("""UPDATE discoveries SET rating_source='ai'
                      WHERE rating_source IS NULL
                      AND rating_reason IS NOT NULL AND TRIM(rating_reason)<>''""")
        db.execute("""UPDATE discoveries SET rating_source='human'
                      WHERE rating_source IS NULL AND rating IN ('S','A','B','C','D','忽略')""")
        db.commit()
    except sqlite3.OperationalError as exc:
        db.rollback()
        if 'duplicate column' not in str(exc).lower():
            raise
    finally:
        db.close()
    return added


def inspect(value):
    path=location(value,require_exists=True)
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5) as db:
        versions,_=metadata(db)
        db.execute('SELECT discovery_id,project_json FROM discoveries LIMIT 1').fetchall()
        db.execute('SELECT event_id,command_id,posted FROM task_outbox LIMIT 1').fetchall()
        db.execute('SELECT x_user_id,retired_at_us FROM target_discovery_ledger LIMIT 1').fetchall()
        return max(versions)

def migrate(value, *, fail_before_commit=False):
    path=location(value)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.parent.stat().st_mode&0o077:raise ValueError('unsafe_hunter_permissions')
    try:
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    except FileExistsError:pass
    location(path,require_exists=True)
    db=sqlite3.connect(path,timeout=5)
    try:
        db.row_factory=sqlite3.Row
        tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables:
            versions,columns=metadata(db,complete=False)
            if max(versions)<LATEST_VERSION:
                from .retention import backup_bundle,micros
                import time
                if 'worker_lease' in tables:
                    lease=db.execute('SELECT expires_at FROM worker_lease WHERE id=1').fetchone()
                    if lease and lease[0]>time.time():raise ValueError('stop_worker_before_migration')
                backup_bundle(path,kind='migration',clock_us=micros(time.time()))
        else:
            if db.execute('PRAGMA application_id').fetchone()[0] not in (0,APP_ID):raise ValueError('foreign_database_refused')
            versions,columns=[],{'version','name','applied_at'}
        db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA busy_timeout=5000')
        db.execute('BEGIN IMMEDIATE')
        try:
            stamp=datetime.now(timezone.utc).isoformat();hashes=checksums()
            if not versions:
                statements(db,(SQL_ROOT/FILES[1]).read_text())
                db.execute("INSERT INTO _store_identity(singleton,store_name) VALUES(1,'hunter')")
            db.execute('CREATE TABLE IF NOT EXISTS _migration_checksums(version INTEGER PRIMARY KEY,sha256 TEXT NOT NULL) STRICT')
            for version in FILES:
                if version not in versions:
                    if version!=1:statements(db,(SQL_ROOT/FILES[version]).read_text())
                    names=['version','name','applied_at']+(['checksum'] if 'checksum' in columns else [])
                    values=[version,NAMES[version],stamp]+([hashes[version]] if 'checksum' in columns else [])
                    db.execute(f"INSERT INTO _schema_migrations({','.join(names)}) VALUES({','.join('?' for _ in names)})",values)
                    if version==2:db.execute('INSERT INTO _hunter_migrations(version,checksum,applied_at) VALUES(2,?,?)',(hashes[2],stamp))
                    if version==3:
                        # Preserve every old row and ID. Ambiguous stable identities require review.
                        targets=db.execute('SELECT target,max(target_id) x_id,max(window_at) seen_at FROM follow_events GROUP BY target').fetchall()
                        for target in targets:
                            ids=[r[0] for r in db.execute('SELECT DISTINCT target_id FROM follow_events WHERE target=? AND target_id IS NOT NULL',(target['target'],))]
                            if len(ids)>1:raise ValueError('legacy_target_identity_review_required')
                            entity='tgt_'+str(uuid.uuid4())
                            db.execute('INSERT INTO target_identities(entity_key,anchor,x_user_id,current_handle,updated_at) VALUES(?,?,?,?,?)',(entity,target['target'],target['x_id'],target['target'],target['seen_at']))
                            db.execute('INSERT INTO target_aliases(x_handle,entity_key) VALUES(?,?)',(target['target'],entity))
                        for row in db.execute('SELECT target,first_discovered_at FROM discoveries').fetchall():
                            db.execute('UPDATE discoveries SET discovery_id=?,updated_at=? WHERE target=?',('dsc_'+str(uuid.uuid4()),row['first_discovered_at'],row['target']))
                        db.execute('INSERT INTO state(key,value) VALUES(?,?)',('cursor_secret','"'+secrets.token_hex(32)+'"'))
                        db.execute("UPDATE task_outbox SET status='failed',public_state='unknown',last_error='legacy_confirmation_protocol_review_required' WHERE command_id IS NULL")
                    if version==4:
                        import json,re
                        from .retention import micros
                        for row in db.execute('SELECT d.*,i.x_user_id FROM discoveries d LEFT JOIN target_identities i ON i.anchor=d.target').fetchall():
                            if not row['x_user_id'] or not re.fullmatch(r'[0-9]{1,40}',row['x_user_id']):raise ValueError('legacy_target_identity_review_required')
                            profile=db.execute('SELECT target_name,description FROM follow_events WHERE target=? ORDER BY id DESC LIMIT 1',(row['target'],)).fetchone()
                            first=micros(row['first_discovered_at'])
                            db.execute('INSERT INTO target_discovery_ledger(scope,platform,x_user_id,discovery_id,first_discovered_at_us) VALUES(?,?,?,?,?)',('ikun-main','x',row['x_user_id'],row['discovery_id'],first))
                            db.execute('UPDATE discoveries SET first_discovered_at_us=?,profile_json=? WHERE discovery_id=?',(first,json.dumps(dict(profile) if profile else {}),row['discovery_id']))
                        for task in db.execute('SELECT id,body FROM task_outbox').fetchall():
                            db.execute('UPDATE task_outbox SET body_hash=? WHERE id=?',(hashlib.sha256(task['body'].encode()).hexdigest(),task['id']))
                        db.execute("INSERT INTO state(key,value) VALUES('retention_clock_highwater','0')")
                db.execute('INSERT OR IGNORE INTO _migration_checksums(version,sha256) VALUES(?,?)',(version,hashes[version]))
            db.execute(f'PRAGMA application_id={APP_ID}');db.execute(f'PRAGMA user_version={LATEST_VERSION}')
            metadata(db)
            if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('hunter_foreign_key_failure')
            if fail_before_commit:raise ValueError('injected_migration_failure')
            db.commit()
        except BaseException:db.rollback();raise
    finally:db.close()
    inspect(path)
