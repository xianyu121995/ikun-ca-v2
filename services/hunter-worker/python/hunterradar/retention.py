"""Hunter-only TTL, verified online backup and monotone recovery fences."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import time
import uuid

PROTOCOL='hunter-research-retention-v1.0.0'
BACKUP_DEADLINE_SECONDS=8
TTL_US=604800_000000
WINDOW_US=259200_000000
SCOPE='ikun-main'

def micros(value):
    if isinstance(value,bool):raise ValueError('invalid_retention_clock')
    try:
        number=Decimal(str(value))
        if not number.is_finite() or number<0:raise ValueError('invalid_retention_clock')
        return int((number*1000000).to_integral_value(rounding=ROUND_DOWN))
    except (InvalidOperation,TypeError):raise ValueError('invalid_retention_clock') from None

def watermark(db,now):
    row=db.execute("SELECT value FROM state WHERE key='retention_clock_highwater'").fetchone()
    return max(micros(now),int(json.loads(row[0])) if row else 0)

def advance(db,now):
    stamp=watermark(db,now)
    db.execute("INSERT INTO state(key,value) VALUES('retention_clock_highwater',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(stamp),))
    return stamp

def active(db,row,now):
    if row is None or row['first_discovered_at_us']+TTL_US<=watermark(db,now):return False
    ledger=db.execute('SELECT retired_at_us FROM target_discovery_ledger WHERE discovery_id=?',(row['discovery_id'],)).fetchone()
    return ledger is not None and ledger[0] is None

def retired(db,x_id,now):
    if not x_id:return False
    row=db.execute("SELECT first_discovered_at_us,retired_at_us FROM target_discovery_ledger WHERE scope=? AND platform='x' AND x_user_id=?",(SCOPE,x_id)).fetchone()
    return bool(row and (row['retired_at_us'] is not None or row['first_discovered_at_us']+TTL_US<=watermark(db,now)))

def _private_directory(path):
    from .migration import location
    location(path/'hunter.db')
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.stat().st_mode&0o077:raise ValueError('unsafe_backup_permissions')

def _write_json(path,value):
    data=(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
    temp=path.with_suffix('.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
        fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if temp.exists():temp.unlink()
    return hashlib.sha256(data).hexdigest()

def _table(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None
def _rows(db,table):return [dict(r) for r in db.execute('SELECT * FROM '+table)] if _table(db,table) else []
def _file_hash(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
COMMAND_FENCE=('id','event_id','command_id','request_hash','body_hash','posted','receipt_id','project_id','receipt_json')

def backup_bundle(path,*,kind,clock_us,expired=()):
    """Source is read-only; caller may hold a reserved writer lock, never use its writer for backup."""
    from .migration import location,metadata
    path=location(path,require_exists=True)
    parent=path.parent/'recovery';_private_directory(parent)
    folder=parent/(kind+'-'+uuid.uuid4().hex);_private_directory(folder)
    target=folder/'hunter.db'
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    started=time.monotonic()
    def progress(*_):
        if time.monotonic()-started>BACKUP_DEADLINE_SECONDS:raise TimeoutError('hunter_backup_deadline')
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5) as source,sqlite3.connect(target,timeout=5) as output:
        source.backup(output,pages=256,progress=progress,sleep=.01)
    with sqlite3.connect(target.as_uri()+'?mode=ro',uri=True,timeout=5) as check:
        check.row_factory=sqlite3.Row
        metadata(check,complete=False)
        if check.execute('PRAGMA quick_check').fetchone()[0]!='ok' or check.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('backup_integrity_failed')
        tables={r[0]:r[1] for r in check.execute('SELECT version,name FROM _schema_migrations')}
        ledger=_rows(check,'target_discovery_ledger')
        commands=[{k:r.get(k) for k in COMMAND_FENCE} for r in _rows(check,'task_outbox')]
        counts={name:check.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('discoveries','task_outbox','operation_receipts') if _table(check,name)}
    with target.open('rb') as stream:os.fsync(stream.fileno())
    manifest={'version':1,'protocol':PROTOCOL,'kind':kind,'created_at_us':clock_us,'highwater_us':clock_us,
              'database_sha256':_file_hash(target),'schema':tables,
              'expired_fences':[dict(r) for r in expired],'ledger_sha256':hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest(),
              'commands':commands,'counts':counts}
    _write_json(folder/'manifest.json',manifest)
    validate_bundle(folder)
    return folder,manifest

def validate_bundle(folder):
    from .migration import location,metadata
    folder=Path(folder).absolute();path=location(folder/'hunter.db',require_exists=True)
    manifest_path=folder/'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_nlink!=1 or manifest_path.stat().st_mode&0o077:raise ValueError('unsafe_backup_manifest')
    data=json.loads(manifest_path.read_text())
    if data.get('version')!=1 or data.get('protocol')!=PROTOCOL or data.get('database_sha256')!=_file_hash(path):raise ValueError('backup_manifest_mismatch')
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5) as db:
        db.row_factory=sqlite3.Row;metadata(db,complete=False)
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('backup_integrity_failed')
        for name,count in data['counts'].items():
            if name not in ('discoveries','task_outbox','operation_receipts') or db.execute('SELECT count(*) FROM '+name).fetchone()[0]!=count:raise ValueError('backup_count_mismatch')
        if hashlib.sha256(json.dumps(_rows(db,'target_discovery_ledger'),sort_keys=True).encode()).hexdigest()!=data['ledger_sha256']:raise ValueError('backup_ledger_mismatch')
        if {str(r[0]):r[1] for r in db.execute('SELECT version,name FROM _schema_migrations')}!={str(k):v for k,v in data['schema'].items()}:raise ValueError('backup_schema_mismatch')
        actual=[{k:r.get(k) for k in COMMAND_FENCE} for r in _rows(db,'task_outbox')]
        if actual!=data['commands']:raise ValueError('backup_commands_mismatch')
    return data

def prune_restore_staging(parent,now_us):
    files=[]
    for path in Path(parent).glob('.hunter-restore-*.tmp'):
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1 or not re.fullmatch(r'\.hunter-restore-[a-f0-9]{32}\.tmp',path.name):continue
        stat=path.stat();files.append((micros(getattr(stat,'st_birthtime',stat.st_mtime)),path))
    for index,(created,path) in enumerate(sorted(files,reverse=True)):
        if index>=3 or created+172800_000000<=now_us:
            for item in (Path(str(path)+'-wal'),Path(str(path)+'-shm'),path):
                if item.exists() and not item.is_symlink() and item.is_file() and item.stat().st_nlink==1:item.unlink()

def prune_bundles(path,now_us,keep=None):
    prune_restore_staging(Path(path).parent,now_us)
    parent=Path(path).parent/'recovery'
    if not parent.exists():return
    _private_directory(parent)
    bundles=[]
    for folder in parent.iterdir():
        if folder.is_symlink() or not folder.is_dir() or not re.fullmatch(r'(?:migration|retention)-[a-f0-9]{32}',folder.name):continue
        valid=True
        try:data=validate_bundle(folder);created=data['created_at_us']
        except (ValueError,OSError,sqlite3.Error,KeyError,TypeError):
            valid=False;created=micros(folder.stat().st_mtime)
            try:created=min(created,int(json.loads((folder/'manifest.json').read_text())['created_at_us']))
            except (ValueError,OSError,KeyError,TypeError):pass
        bundles.append((created,folder,valid))
    for index,(created,folder,valid) in enumerate(sorted(bundles,reverse=True)):
        if folder!=keep and (index>=3 or created+172800_000000<=now_us):
            if not valid:_write_json(parent/('failed-'+folder.name+'.json'),{'bundle_id':folder.name,'failure':'backup_validation_failed','created_at_us':created,'retired_at_us':now_us})
            shutil.rmtree(folder)

def _purge(db,rows,stamp):
    for row in rows:
        identifier=row['discovery_id'];target=row['target']
        db.execute('UPDATE target_discovery_ledger SET retired_at_us=COALESCE(retired_at_us,?) WHERE discovery_id=?',(stamp,identifier))
        db.execute("UPDATE task_outbox SET body=CASE WHEN posted=0 AND command_id IS NOT NULL AND status IN ('pending','delivering','unknown') THEN body ELSE '{}' END,target=NULL WHERE discovery_id=?",(identifier,))
        db.execute("DELETE FROM public_changes WHERE type='hunter.discovery.updated' AND entity_id=?",(identifier,))
        db.execute('DELETE FROM follow_events WHERE target=?',(target,))
        db.execute('DELETE FROM seen_targets WHERE target=?',(target,))
        db.execute('DELETE FROM target_aliases WHERE entity_key IN (SELECT entity_key FROM target_identities WHERE anchor=?)',(target,))
        db.execute('DELETE FROM target_identities WHERE anchor=?',(target,))
        db.execute('DELETE FROM discoveries WHERE discovery_id=?',(identifier,))

def cleanup(store,now=None,*,failpoint=None):
    now=time.time() if now is None else now
    store.retention_clock(now) # TTL fences survive a failed backup/delete transaction.
    prune_bundles(store.path,micros(store.retention_clock(now)))
    with store.transaction() as db:
        stamp=advance(db,now)
        rows=[dict(r) for r in db.execute('SELECT target,discovery_id,first_discovered_at_us FROM discoveries WHERE first_discovered_at_us<=? ORDER BY first_discovered_at_us,discovery_id LIMIT 500',(stamp-TTL_US,))]
        obsolete=db.execute('SELECT 1 FROM follow_events WHERE window_at<? LIMIT 1',((stamp-WINDOW_US)/1e6,)).fetchone() or db.execute('SELECT 1 FROM operation_receipts WHERE expires_at<=? LIMIT 1',(stamp/1e6,)).fetchone() or db.execute("SELECT 1 FROM task_outbox WHERE target IS NULL AND body<>'{}' AND (posted=1 OR status NOT IN ('pending','delivering','unknown')) LIMIT 1").fetchone()
        if not rows and not obsolete:
            prune_bundles(store.path,stamp)
            return {'deleted':0,'backup':None}
        fences=[dict(db.execute('SELECT * FROM target_discovery_ledger WHERE discovery_id=?',(r['discovery_id'],)).fetchone()) for r in rows]
        folder,manifest=backup_bundle(store.path,kind='retention',clock_us=stamp,expired=fences)
        if failpoint=='after_backup':raise RuntimeError('injected_cleanup_after_backup')
        _purge(db,rows,stamp)
        db.execute('DELETE FROM follow_events WHERE id IN (SELECT id FROM follow_events WHERE window_at<? LIMIT 5000)',((stamp-WINDOW_US)/1e6,))
        db.execute('DELETE FROM operation_receipts WHERE expires_at<=?',(stamp/1e6,))
        # A late receipt may make a previously retained, unposted snapshot unnecessary.
        db.execute("UPDATE task_outbox SET body='{}' WHERE target IS NULL AND (posted=1 OR status NOT IN ('pending','delivering','unknown'))")
        batch=folder.name
        db.execute('INSERT INTO retention_runs(batch_id,completed_at_us,manifest_sha256,discoveries_deleted) VALUES(?,?,?,?)',(batch,stamp,hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(),len(rows)))
        if failpoint=='before_commit':raise RuntimeError('injected_cleanup_before_commit')
        if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('cleanup_foreign_key_failure')
    prune_bundles(store.path,stamp,keep=folder)
    return {'deleted':len(rows),'backup':str(folder),'batch_id':batch}

def restore_bundle(folder,destination,*,current,progress=None):
    """Require an intact latest source for post-backup fences. Never guess missing future state."""
    from .migration import inspect,location,metadata
    manifest=validate_bundle(folder)
    if current is None:raise ValueError('latest_recovery_fences_required')
    current=location(current,require_exists=True);inspect(current)
    if os.path.samefile(current,Path(folder)/'hunter.db') or (current.parent/'manifest.json').exists():raise ValueError('current_must_be_offline_latest_source_not_backup')
    destination=location(destination)
    if destination.exists():raise ValueError('restore_destination_must_be_new')
    with sqlite3.connect(current,timeout=5) as source:
        source.execute('BEGIN IMMEDIATE')
        source.row_factory=sqlite3.Row
        lease=source.execute('SELECT expires_at FROM worker_lease WHERE id=1').fetchone()
        if lease and lease[0]>time.time():raise ValueError('stop_worker_before_restore')
        ledger=_rows(source,'target_discovery_ledger');tasks=_rows(source,'task_outbox');receipts=_rows(source,'operation_receipts')
        revisions={r['discovery_id']:r['version'] for r in source.execute('SELECT discovery_id,version FROM discoveries')}
        allocated=source.execute("SELECT seq FROM sqlite_sequence WHERE name='public_changes'").fetchone()
        event_floor=max(allocated[0] if allocated else 0,source.execute('SELECT COALESCE(max(sequence),0) FROM public_changes').fetchone()[0])
        states={r['key']:r['value'] for r in source.execute('SELECT key,value FROM state') if r['key'].startswith(('provider_intent:','cooldown:','hunter_sample:'))}
        quotas=_rows(source,'quota');clock=watermark(source,time.time())
        if manifest['schema'].get('4')!='hunter_research_retention':raise ValueError('restore_schema4_bundle_required')
        source_version=max(metadata(source)[0]);bundle_version=max(int(v) for v in manifest['schema'])
        if source_version!=bundle_version:raise ValueError('restore_schema_version_mismatch')
        if source_version>=5:
            # Never forget a committed offline import's durable IDs/checkpoints.
            # The mutable seen-time projection is cleaned by the normal TTL path.
            with sqlite3.connect((Path(folder)/'hunter.db').absolute().as_uri()+'?mode=ro',uri=True,timeout=5) as check:
                check.row_factory=sqlite3.Row
                for name in ('hunter_takeover_runs','hunter_takeover_rows','hunter_takeover_conflicts','hunter_takeover_project_refs'):
                    snapshot_rows=sorted(json.dumps(r,sort_keys=True) for r in _rows(check,name))
                    current_rows=sorted(json.dumps(r,sort_keys=True) for r in _rows(source,name))
                    if snapshot_rows!=current_rows:raise ValueError('restore_takeover_checkpoint_mismatch')
                # Same schema number does not make an older directory/proof
                # checkpoint safe. Never resurrect a deleted or edited account.
                prefix = 'legacy_takeover_v2:'
                def directory_state(db):
                    return {r['key']: r['value'] for r in db.execute('SELECT key,value FROM state WHERE key GLOB ?', (prefix+'*',))}
                saved, latest = directory_state(check), directory_state(source)
                if saved != latest:
                    raise ValueError('restore_legacy_directory_checkpoint_mismatch')
                for key in latest:
                    if key.startswith(prefix+'account:'):
                        identifier = key.removeprefix(prefix+'account:')
                        a = check.execute('SELECT * FROM hunters WHERE id=?', (identifier,)).fetchone()
                        b = source.execute('SELECT * FROM hunters WHERE id=?', (identifier,)).fetchone()
                        if (dict(a) if a else None) != (dict(b) if b else None):
                            raise ValueError('restore_legacy_directory_account_mismatch')
        _private_directory(destination.parent)
        prune_restore_staging(destination.parent,max(clock,manifest['highwater_us']))
        # A non-hunter.db filename is permanently inadmissible to Store/serve, even after SIGKILL.
        staging=destination.parent/('.hunter-restore-'+uuid.uuid4().hex+'.tmp')
        fd=os.open(staging,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        try:
            with sqlite3.connect((Path(folder)/'hunter.db').absolute().as_uri()+'?mode=ro',uri=True,timeout=5) as snapshot,sqlite3.connect(staging,timeout=5) as db:snapshot.backup(db)
            snapshot.close();db.close()
            if progress:progress('after_copy')
            with sqlite3.connect(staging,timeout=5) as db:
                db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
                for row in ledger:
                    old=db.execute('SELECT * FROM target_discovery_ledger WHERE x_user_id=?',(row['x_user_id'],)).fetchone()
                    if old and (old['discovery_id']!=row['discovery_id'] or old['first_discovered_at_us']!=row['first_discovered_at_us']):raise ValueError('recovery_ledger_conflict')
                    if not old:db.execute('INSERT INTO target_discovery_ledger(scope,platform,x_user_id,discovery_id,first_discovered_at_us,retired_at_us) VALUES(?,?,?,?,?,?)',tuple(row[k] for k in ('scope','platform','x_user_id','discovery_id','first_discovered_at_us','retired_at_us')))
                    elif row['retired_at_us'] is not None:db.execute('UPDATE target_discovery_ledger SET retired_at_us=COALESCE(retired_at_us,?) WHERE x_user_id=?',(row['retired_at_us'],row['x_user_id']))
                for row in tasks:
                    old=db.execute('SELECT * FROM task_outbox WHERE id=?',(row['id'],)).fetchone()
                    if old and any(old[k]!=row[k] for k in ('event_id','command_id','request_hash','body_hash')):raise ValueError('recovery_command_conflict')
                    if old and old['posted'] and not row['posted']:raise ValueError('recovery_posted_regression')
                    if old and (any(old[k] is not None and old[k]!=row[k] for k in ('project_id','receipt_id')) or old['command_revision']>row['command_revision']):raise ValueError('recovery_receipt_regression')
                    names=list(row);db.execute('INSERT OR REPLACE INTO task_outbox('+','.join(names)+') VALUES('+','.join('?' for _ in names)+')',tuple(row.values()))
                for row in receipts:
                    old=db.execute('SELECT * FROM operation_receipts WHERE actor_id=? AND scope=? AND route=? AND request_key=?',tuple(row[k] for k in ('actor_id','scope','route','request_key'))).fetchone()
                    if old and any(old[k]!=row[k] for k in ('body_hash','status','response_json','etag')):raise ValueError('recovery_receipt_conflict')
                    names=list(row);db.execute('INSERT OR REPLACE INTO operation_receipts('+','.join(names)+') VALUES('+','.join('?' for _ in names)+')',tuple(row.values()))
                for key,value in states.items():db.execute('INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
                for row in quotas:db.execute('INSERT INTO quota(provider,window,reserved) VALUES(?,?,?) ON CONFLICT(provider,window) DO UPDATE SET reserved=max(reserved,excluded.reserved)',(row['provider'],row['window'],row['reserved']))
                stamp=advance(db,max(clock,manifest['highwater_us'])/1e6)
                for fence in manifest['expired_fences']:db.execute('UPDATE target_discovery_ledger SET retired_at_us=COALESCE(retired_at_us,?) WHERE discovery_id=?',(stamp,fence['discovery_id']))
                expired=[dict(r) for r in db.execute('SELECT d.* FROM discoveries d JOIN target_discovery_ledger l USING(discovery_id) WHERE d.first_discovered_at_us<=? OR l.retired_at_us IS NOT NULL',(stamp-TTL_US,))]
                _purge(db,expired,stamp)
                for row in db.execute('SELECT discovery_id,version FROM discoveries').fetchall():
                    db.execute('UPDATE discoveries SET version=?,updated_at=? WHERE discovery_id=?',(max(row['version'],revisions.get(row['discovery_id'],0))+1,stamp/1e6,row['discovery_id']))
                db.execute('DELETE FROM public_changes')
                # Preserve assigned IDs including deleted holes and command events sharing this stream.
                sequence=db.execute("SELECT seq FROM sqlite_sequence WHERE name='public_changes'").fetchone()
                if sequence:db.execute("UPDATE sqlite_sequence SET seq=max(seq,?) WHERE name='public_changes'",(event_floor,))
                else:db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('public_changes',?)",(event_floor,))
                db.execute("UPDATE state SET value=? WHERE key='cursor_secret'",(json.dumps(uuid.uuid4().hex+uuid.uuid4().hex),))
                # New discoveries after the snapshot have a ledger but no copied business content: fail closed per target.
                db.execute('DELETE FROM worker_lease');db.execute("UPDATE state SET value='false' WHERE key='worker_heartbeat'")
                if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('restore_foreign_key_failure')
                if progress:progress('before_merge_commit')
            if progress:progress('after_merge_commit')
            if db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:raise ValueError('restore_checkpoint_busy')
            db.close()
            with sqlite3.connect(staging.as_uri()+'?mode=ro',uri=True,timeout=5) as verification:
                metadata(verification)
                if verification.execute('PRAGMA quick_check').fetchone()[0]!='ok' or verification.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('restore_integrity_failed')
            verification.close()
            with staging.open('rb') as stream:os.fsync(stream.fileno())
            # Reserve this new destination exclusively. Before replace it is invalid/empty;
            # after replace it contains all validated fences. No valid intermediate DB exists.
            fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            reserved=os.fstat(fd);os.close(fd)
            if progress:progress('after_reservation')
            actual=destination.stat()
            if (reserved.st_dev,reserved.st_ino)!=(actual.st_dev,actual.st_ino) or actual.st_size:raise ValueError('restore_destination_changed')
            os.replace(staging,destination)
            parent_fd=os.open(destination.parent,os.O_RDONLY)
            try:os.fsync(parent_fd)
            finally:os.close(parent_fd)
            if progress:progress('after_publish')
            inspect(destination)
            return {'restored':True,'ledger':len(ledger),'commands':len(tasks),'highwater_us':stamp}
        except BaseException:
            # Preserve inadmissible staging evidence. A hard kill needs no catch/marker to be safe.
            raise
