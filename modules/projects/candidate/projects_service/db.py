import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import CoreProjectFields, ProjectFields, normalize_website

APPLICATION_ID = 0x494B0203  # packages/runtime's projects store marker
FIELDS = tuple(ProjectFields.model_fields)
PUBLIC_FIELDS = ('id', *FIELDS, 'discovered_at', 'created_at', 'updated_at', 'version')
SORTS = {
    'updated': 'updated_at DESC, id ASC',
    'discovered_desc': 'discovered_at DESC, id ASC',
    'discovered_asc': 'discovered_at ASC, id ASC',
    'rating': "CASE rating WHEN 'S' THEN 0 WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 3 END, updated_at DESC, id ASC",
    'token_date': 'token_date IS NULL, token_date ASC, id ASC',
    'name': 'name COLLATE NOCASE ASC, id ASC',
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class DomainError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def project_path(value):
    path = Path(value).expanduser().absolute()
    if path.name != 'projects.db':
        raise ValueError('数据库必须是独立的 projects.db 普通文件')
    for candidate in (*path.parents, path, Path(str(path) + '-wal'), Path(str(path) + '-shm')):
        if candidate.is_symlink() or (candidate.is_file() and candidate.stat().st_nlink != 1):
            raise ValueError('数据库路径及 sidecar 不允许符号链接或硬链接')
    for candidate in (path,Path(str(path)+'-wal'),Path(str(path)+'-shm')):
        if candidate.exists() and not candidate.is_file():
            raise ValueError('数据库及 sidecar 必须是普通文件')
    return path


class Database:
    def __init__(self, path):
        self.path = project_path(path)

    @contextmanager
    def connect(self):
        # mode=rw never silently creates a wrongly configured database during API requests.
        project_path(self.path)
        con = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            if con.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID:
                raise RuntimeError('拒绝打开未标记为主页项目库的数据库')
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA busy_timeout=5000')
            yield con
        finally:
            con.close()

    @contextmanager
    def transaction(self):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            try:
                yield con
                con.commit()
            except BaseException:
                con.rollback()
                raise

    def migrate(self):
        project_path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        if self.path.is_symlink():
            raise ValueError('数据库不允许使用符号链接')
        con = sqlite3.connect(self.path, timeout=3)
        try:
            marker = con.execute('PRAGMA application_id').fetchone()[0]
            tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if marker not in (0, APPLICATION_ID) or (marker == 0 and tables):
                raise RuntimeError('拒绝迁移其他业务库或未标记的已有数据库')
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA synchronous=FULL')
            # The schema ledger and the application marker are committed with each migration.
            for path in sorted(Path(__file__).with_name('migrations').glob('*.sql')):
                sql = path.read_text()
                checksum = digest(sql)
                con.execute('BEGIN IMMEDIATE')
                try:
                    con.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)')
                    applied = con.execute('SELECT checksum FROM schema_migrations WHERE version=?', (path.stem,)).fetchone()
                    if applied:
                        if applied[0] != checksum:
                            raise RuntimeError(f'迁移校验失败: {path.stem}')
                    else:
                        # Individual statements keep the lock and avoid executescript's implicit commit.
                        for statement in sql.split(';'):
                            if statement.strip():
                                con.execute(statement)
                        con.execute('INSERT INTO schema_migrations VALUES (?,?,?)', (path.stem, checksum, now()))
                    con.execute(f'PRAGMA application_id={APPLICATION_ID}')
                    con.commit()
                except BaseException:
                    con.rollback()
                    raise
        finally:
            con.close()

    def create_principal(self, role=None, source=None, tenant='default'):
        if source is not None:
            if role is not None or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',source):
                raise ValueError('服务身份须绑定来源，不能具有用户角色')
            kind = 'service'
        else:
            if role not in ('superadmin','user'):
                raise ValueError('用户角色只能是 superadmin 或 user')
            kind = 'user'
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', tenant):
            raise ValueError('租户 ID 不正确')
        token = secrets.token_urlsafe(48)
        principal_id = str(uuid.uuid4())
        with self.transaction() as con:
            con.execute('INSERT INTO principals(id,tenant_id,token_hash,kind,role,source,created_at) VALUES (?,?,?,?,?,?,?)',
                        (principal_id, tenant, digest(token), kind, role, source, now()))
        return principal_id, token


def public(row):
    return {key: row[key] for key in PUBLIC_FIELDS}


def get_project(con, project_id, tenant='default', *, include_removed=False, full=False):
    row = con.execute('SELECT * FROM projects WHERE id=? AND tenant_id=?', (project_id, tenant)).fetchone()
    if row is None:
        raise DomainError(404, 'not_found', '项目不存在')
    if row['deleted_at'] and not include_removed:
        raise DomainError(410, 'project_deleted', '主页项目已删除，重复导入不会恢复它')
    return dict(row) if full else public(row)


def audit(con, actor, action, project_id, fields, tenant='default'):
    con.execute('INSERT INTO audit_log(tenant_id,actor_id,action,project_id,changed_fields,created_at) VALUES (?,?,?,?,?,?)',
                (tenant, actor, action, project_id, json.dumps(sorted(fields)), now()))
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_changes'").fetchone():
        row=con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone()
        con.execute('INSERT INTO project_changes(project_id,tenant_id,record_json,created_at) VALUES(?,?,?,?)',
                    (project_id,tenant,json.dumps(dict(row),ensure_ascii=False),now()))


def insert_project(con, fields, actor, tenant='default', *, extras=None):
    data = fields.model_dump(mode='json')
    stamp = now()
    project_id = 'prj_' + str(uuid.uuid4())
    key = normalize_website(data['website'])[1]
    if key:
        existing = con.execute('SELECT id,deleted_at FROM projects WHERE website_key=? AND tenant_id=?', (key,tenant)).fetchone()
        if existing:
            if existing['deleted_at']:
                raise DomainError(410, 'project_deleted', '同一官网的主页项目已删除')
            raise DomainError(409, 'duplicate_project', '该官网已存在，请编辑原项目或通过来源导入关联')
    columns = ('id', 'tenant_id', *FIELDS, 'website_key', 'discovered_at', 'created_at', 'updated_at')
    values = (project_id, tenant, *(data[f] for f in FIELDS), key, stamp, stamp, stamp)
    con.execute(f"INSERT INTO projects({','.join(columns)}) VALUES ({','.join('?' for _ in values)})", values)
    if extras:
        allowed={'category','progress_percent','home_membership','discovered_at'}
        if set(extras)-allowed:
            raise ValueError('INVALID_PROJECT_EXTRA')
        con.execute(f"UPDATE projects SET {','.join(f'{key}=?' for key in extras)} WHERE id=?",(*extras.values(),project_id))
    audit(con, actor, 'create', project_id, FIELDS, tenant)
    return get_project(con, project_id, tenant)


def create_project(con, fields, actor, key, tenant='default'):
    request_hash = digest(json.dumps(fields.model_dump(mode='json'), sort_keys=True))
    receipt = con.execute('SELECT * FROM write_receipts WHERE principal_id=? AND idempotency_key=?', (actor, key)).fetchone()
    if receipt:
        if receipt['request_hash'] != request_hash:
            raise DomainError(409, 'idempotency_conflict', '同一幂等键不能用于不同的项目资料')
        return get_project(con, receipt['project_id'], tenant), False
    project = insert_project(con, fields, actor, tenant)
    con.execute('INSERT INTO write_receipts VALUES (?,?,?,?,?)', (actor, key, request_hash, project['id'], now()))
    return project, True


def import_project(con, data, actor, tenant='default', *, include_removed=False, extras=None):
    receipt = con.execute('SELECT project_id FROM project_sources WHERE source=? AND external_id=? AND tenant_id=?',
                          (data.source, data.external_id, tenant)).fetchone()
    if receipt:
        if data.project_id and data.project_id != receipt['project_id']:
            raise DomainError(409, 'mapping_conflict', '同一来源记录不能改绑另一个项目')
        return get_project(con, receipt['project_id'], tenant,include_removed=include_removed), False
    key = normalize_website(data.project.website)[1]
    existing = con.execute('SELECT id FROM projects WHERE website_key=? AND tenant_id=?', (key,tenant)).fetchone() if key else None
    if data.project_id:
        project = get_project(con, data.project_id, tenant,include_removed=include_removed)
        if existing and existing['id'] != data.project_id:
            raise DomainError(409, 'mapping_conflict', '官网与指定项目指向不同记录，需要人工核对')
        created = False
    else:
        created = existing is None
        project = insert_project(con, data.project, actor, tenant,extras=extras) if created else get_project(con, existing['id'], tenant,include_removed=include_removed)
    con.execute('INSERT INTO project_sources(tenant_id,source,external_id,project_id,added_by,added_at) VALUES (?,?,?,?,?,?)', (tenant, data.source, data.external_id, project['id'], actor, now()))
    audit(con, actor, 'import_link', project['id'], ('source', 'external_id'), tenant)
    return project, created


def patch_project(con, project_id, patch, actor, tenant='default', *, include_removed=False, extras=None):
    current = get_project(con, project_id, tenant,include_removed=include_removed)
    if current['version'] != patch.expected_version:
        raise DomainError(409, 'version_conflict', '项目已被修改，请刷新后重试')
    changes = patch.model_dump(mode='json', exclude_unset=True, exclude={'expected_version'})
    merged = (CoreProjectFields if include_removed else ProjectFields).model_validate({**{f: current[f] for f in FIELDS}, **changes}).model_dump(mode='json')
    assignments = {**merged, 'website_key': normalize_website(merged['website'])[1], 'updated_at': now()}
    if extras:
        if set(extras)-{'category','progress_percent','home_membership'}:
            raise ValueError('INVALID_PROJECT_EXTRA')
        assignments.update(extras)
    if assignments['website_key']:
        duplicate = con.execute('SELECT id FROM projects WHERE website_key=? AND id!=? AND tenant_id=?', (assignments['website_key'], project_id, tenant)).fetchone()
        if duplicate:
            raise DomainError(409, 'duplicate_project', '该官网已关联其他主页项目')
    con.execute(f"UPDATE projects SET {','.join(f'{f}=?' for f in assignments)},version=version+1 WHERE id=? AND version=?",
                (*assignments.values(), project_id, patch.expected_version))
    audit(con, actor, 'update', project_id, set(changes)|set(extras or {}), tenant)
    return get_project(con, project_id, tenant,include_removed=include_removed)


def delete_project(con, project_id, version, actor, tenant='default', *, home_action=None):
    current = get_project(con, project_id, tenant,include_removed=home_action is not None)
    if current['version'] != version:
        raise DomainError(409, 'version_conflict', '项目已被修改，请刷新后重试')
    stamp = now()
    if home_action is not None:
        if home_action not in ('active','removed'):
            raise ValueError('INVALID_MEMBERSHIP')
        row=con.execute('SELECT home_membership FROM projects WHERE id=?',(project_id,)).fetchone()
        if row['home_membership']!=home_action:
            con.execute('UPDATE projects SET home_membership=?,updated_at=?,version=version+1 WHERE id=?',(home_action,stamp,project_id))
            audit(con,actor,'home.'+home_action,project_id,('home_membership',),tenant)
        return
    con.execute('UPDATE projects SET deleted_at=?,updated_at=?,version=version+1 WHERE id=?', (stamp, stamp, project_id))
    audit(con, actor, 'delete', project_id, ('deleted_at',), tenant)


def project_predicates(con,q='',rating=None,progress=None,tenant='default',*,include_removed=False,membership=None):
    clauses,args=['tenant_id=?'],[tenant]
    if not include_removed:
        clauses.append('deleted_at IS NULL')
    if membership:
        clauses.append('home_membership=?');args.append(membership)
    if q:
        # LIKE metacharacters are literal text, not an uncontrolled wildcard query.
        escaped = q.casefold().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        con.create_function('casefold', 1, lambda value: str(value).casefold(), deterministic=True)
        clauses.append("(" + ' OR '.join(f"casefold({field}) LIKE ? ESCAPE '\\'" for field in ('name','description','website','notes')) + ")")
        args.extend([f'%{escaped}%'] * 4)
    for field, value in (('rating', rating), ('progress', progress)):
        if value:
            clauses.append(f'{field}=?')
            args.append(value)
    return clauses,args


def list_projects(con, q='', rating=None, progress=None, sort='updated', limit=20, offset=0, tenant='default'):
    clauses,args=project_predicates(con,q,rating,progress,tenant)
    where = ' AND '.join(clauses)
    # Count + page are read from a single SQLite snapshot.
    con.execute('BEGIN')
    total = con.execute(f'SELECT COUNT(*) FROM projects WHERE {where}', args).fetchone()[0]
    rows = con.execute(f'SELECT * FROM projects WHERE {where} ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
    con.commit()
    return {'items': [public(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset, 'server_time': now()}
