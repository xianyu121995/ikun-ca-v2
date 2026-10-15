"""Explicit B2 migrations. The website/health path never calls this module's migrate()."""
import hashlib
import json
import os
import secrets
import sqlite3
from pathlib import Path
from contextlib import contextmanager

from .db import APPLICATION_ID, Database, now, project_path

SQL_ROOT = Path(__file__).resolve().parents[4] / 'schemas/projects'
SCOPE = 'ikun-main'
FOUNDATION_SQL = (SQL_ROOT/'001_foundation.sql').read_text()
FOUNDATION_HASH = hashlib.sha256(FOUNDATION_SQL.encode()).hexdigest()


def statements(con, sql):
    pending = ''
    for line in sql.splitlines(True):
        pending += line
        if sqlite3.complete_statement(pending):
            con.execute(pending)
            pending = ''
    if pending.strip():
        raise RuntimeError('INCOMPLETE_MIGRATION')


def location(value):
    path = project_path(value)
    if path.parent.name != 'projects':
        raise ValueError('PROJECTS_STORAGE_LAYOUT_REJECTED')
    return path


def metadata(con, *, require_business=True):
    if con.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID:
        raise RuntimeError('FOREIGN_DATABASE_REJECTED')
    cols = {row[1] for row in con.execute('PRAGMA table_info(_schema_migrations)')}
    if not {'version','name','applied_at'} <= cols or cols - {'version','name','applied_at','checksum'}:
        raise RuntimeError('UNSUPPORTED_MIGRATION_METADATA')
    identity = con.execute('SELECT store_name FROM _store_identity WHERE singleton=1').fetchone()
    if not identity or identity[0] != 'projects':
        raise RuntimeError('STORE_OWNER_MISMATCH')
    rows = con.execute('SELECT version,name FROM _schema_migrations ORDER BY version').fetchall()
    if not rows or rows[0][1]!='foundation':
        raise RuntimeError('FOUNDATION_MIGRATION_MISMATCH')
    versions = [row[0] for row in rows]
    if versions not in ([1],[1,2]) or con.execute('PRAGMA user_version').fetchone()[0] > 2:
        raise RuntimeError('UNSUPPORTED_SCHEMA_VERSION')
    if 2 in versions and (rows[-1][1]!='projects_b2' or con.execute('PRAGMA user_version').fetchone()[0]!=2):
        raise RuntimeError('PROJECTS_MIGRATION_MISMATCH')
    hashes = dict(con.execute('SELECT version,sha256 FROM _migration_checksums'))
    if set(hashes)!=set(versions):raise RuntimeError('UNSUPPORTED_CHECKSUM_METADATA')
    if hashes.get(1) != FOUNDATION_HASH:
        raise RuntimeError('FOUNDATION_CHECKSUM_MISMATCH')
    if 2 in versions:
        expected = hashlib.sha256((SQL_ROOT/'002_projects.sql').read_bytes()).hexdigest()
        if hashes.get(2) != expected:
            raise RuntimeError('PROJECTS_CHECKSUM_MISMATCH')
    elif require_business:
        raise RuntimeError('PROJECTS_MIGRATION_REQUIRED')


class FormalDatabase(Database):
    def __init__(self, value):
        super().__init__(location(value))

    @contextmanager
    def connect(self):
        if self.path.parent.stat().st_mode & 0o077 or self.path.stat().st_mode & 0o077:
            raise RuntimeError('UNSAFE_PROJECTS_PERMISSIONS')
        with super().connect() as con:
            metadata(con)
            yield con

    def inspect(self):
        location(self.path)
        if self.path.parent.stat().st_mode & 0o077 or self.path.stat().st_mode & 0o077:
            raise RuntimeError('UNSAFE_PROJECTS_PERMISSIONS')
        con = sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=5)
        try:
            metadata(con)
            # Concrete business schema admission, not merely SELECT 1.
            con.execute('SELECT id,home_membership,version FROM projects LIMIT 1').fetchall()
            con.execute('SELECT command_id,state FROM tracking_outbox LIMIT 1').fetchall()
            con.execute('SELECT project_id,date,hour,title,status FROM project_milestones LIMIT 1').fetchall()
            con.execute('SELECT completion_id,previous_stage,previous_percent,restore_basis,restored_at FROM project_completions LIMIT 1').fetchall()
        finally:
            con.close()

    def migrate(self, *, fail_before_commit=False):
        location(self.path)
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.path.parent.stat().st_mode & 0o077:
            raise RuntimeError('UNSAFE_PROJECTS_DIRECTORY')
        try:
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.close(fd)
        except FileExistsError:
            if self.path.stat().st_mode & 0o077:
                raise RuntimeError('UNSAFE_PROJECTS_FILE')
        con=sqlite3.connect(self.path,timeout=5)
        con.row_factory=sqlite3.Row
        try:
            tables={row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            marker=con.execute('PRAGMA application_id').fetchone()[0]
            if marker not in (0,APPLICATION_ID) or (marker==0 and tables):
                raise RuntimeError('FOREIGN_DATABASE_REJECTED')
            legacy='projects' in tables and '_schema_migrations' not in tables
            if legacy or ('schema_migrations' in tables and 'operation_receipts' not in tables):
                expected={p.stem:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).with_name('migrations').glob('*.sql')}
                actual=dict(con.execute('SELECT version,checksum FROM schema_migrations'))
                if actual!=expected:
                    raise RuntimeError('LEGACY_CHECKSUM_MISMATCH')
                for name in ('principals','sessions'):
                    if name in tables and con.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]:
                        raise RuntimeError('LEGACY_IDENTITY_RETIREMENT_REQUIRED')
                # No silent scope merging or data truncation.
                for row in con.execute('SELECT tenant_id,length(description),length(notes) FROM projects'):
                    if row[0] not in ('default',SCOPE) or max(row[1],row[2])>4000:
                        raise RuntimeError('LEGACY_DATA_REVIEW_REQUIRED')
            elif '_schema_migrations' in tables:
                # Older foundation has no checksum registry; explicit migration may add it.
                if '_migration_checksums' not in tables:
                    versions=[r[0] for r in con.execute('SELECT version FROM _schema_migrations')]
                    if versions!=[1] or con.execute('PRAGMA user_version').fetchone()[0]>1:
                        raise RuntimeError('UNSUPPORTED_SCHEMA_VERSION')
                else:
                    metadata(con,require_business=False)
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('PRAGMA synchronous=FULL')
            con.execute('PRAGMA busy_timeout=5000')
            con.execute('PRAGMA foreign_keys=OFF')
            con.execute('BEGIN IMMEDIATE')
            try:
                statements(con,FOUNDATION_SQL)
                con.execute('CREATE TABLE IF NOT EXISTS _migration_checksums(version INTEGER PRIMARY KEY,sha256 TEXT NOT NULL) STRICT')
                con.execute("INSERT OR IGNORE INTO _store_identity(singleton,store_name) VALUES(1,'projects')")
                if con.execute('SELECT store_name FROM _store_identity WHERE singleton=1').fetchone()[0]!='projects':
                    raise RuntimeError('STORE_OWNER_MISMATCH')
                columns={row[1] for row in con.execute('PRAGMA table_info(_schema_migrations)')}
                if not con.execute('SELECT 1 FROM _schema_migrations WHERE version=1').fetchone():
                    names=['version','name','applied_at']+(['checksum'] if 'checksum' in columns else [])
                    vals=[1,'foundation',now()]+([FOUNDATION_HASH] if 'checksum' in columns else [])
                    con.execute(f"INSERT INTO _schema_migrations({','.join(names)}) VALUES({','.join('?' for _ in vals)})",vals)
                con.execute('INSERT OR IGNORE INTO _migration_checksums(version,sha256) VALUES(1,?)',(FOUNDATION_HASH,))
                if not con.execute('SELECT 1 FROM _schema_migrations WHERE version=2').fetchone():
                    old='projects' in tables
                    if old:
                        for name in ('sessions','principals'):
                            if name in tables:con.execute(f'DROP TABLE {name}')
                        for name in ('projects','project_sources','audit_log','write_receipts'):
                            if name in tables:
                                con.execute(f'ALTER TABLE {name} RENAME TO legacy_{name}_v1')
                    sql=(SQL_ROOT/'002_projects.sql').read_text()
                    statements(con,sql)
                    if old:
                        cols=('id','tenant_id','name','rating','description','website','website_key','notes','progress','token_date','token_date_status','discovered_at','created_at','updated_at','version','deleted_at')
                        for row in con.execute('SELECT * FROM legacy_projects_v1').fetchall():
                            values=[SCOPE if name=='tenant_id' else row[name] for name in cols]
                            con.execute(f"INSERT INTO projects({','.join(cols)},home_membership) VALUES({','.join('?' for _ in values)},?)",(*values,'removed' if row['deleted_at'] else 'active'))
                        for row in con.execute('SELECT * FROM legacy_project_sources_v1').fetchall():
                            con.execute('INSERT INTO project_sources(tenant_id,source,external_id,project_id,added_by,added_at) VALUES(?,?,?,?,?,?)',(SCOPE,row['source'],row['external_id'],row['project_id'],row['added_by'],row['added_at']))
                        for row in con.execute('SELECT * FROM legacy_audit_log_v1').fetchall():
                            con.execute('INSERT INTO audit_log(id,tenant_id,actor_id,action,project_id,changed_fields,created_at) VALUES(?,?,?,?,?,?,?)',(row['id'],SCOPE,row['actor_id'],row['action'],row['project_id'],row['changed_fields'],row['created_at']))
                    con.execute('INSERT INTO project_settings(key,value) VALUES(?,?)',('cursor_secret',secrets.token_hex(32)))
                    names=['version','name','applied_at']+(['checksum'] if 'checksum' in columns else [])
                    checksum=hashlib.sha256(sql.encode()).hexdigest()
                    vals=[2,'projects_b2',now()]+([checksum] if 'checksum' in columns else [])
                    con.execute(f"INSERT INTO _schema_migrations({','.join(names)}) VALUES({','.join('?' for _ in vals)})",vals)
                    con.execute('INSERT INTO _migration_checksums(version,sha256) VALUES(2,?)',(checksum,))
                con.execute(f'PRAGMA application_id={APPLICATION_ID}')
                con.execute('PRAGMA user_version=2')
                metadata(con)
                if con.execute('PRAGMA foreign_key_check').fetchall():
                    raise RuntimeError('PROJECTS_FOREIGN_KEY_FAILURE')
                if fail_before_commit:
                    raise RuntimeError('INJECTED_MIGRATION_FAILURE')
                con.commit()
            except BaseException:
                con.rollback()
                raise
        finally:
            con.close()
