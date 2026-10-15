#!/usr/bin/env python3
"""Render guarded NEW worker jobs; never install, migrate, or enable external collection."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit

ACCOUNT_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
TARGET = ACCOUNT_HOME / 'Library/Application Support/ikun-ca-v2-c0-lite'
DOMAINS = {'hunter': 4011, 'tracking': 4012}
PROVIDER_KEYS = {'OPENNEWS_TOKEN', 'TWITTERAPI_IO_API_KEY', 'IKUN_TRACKING_6551_TOKEN',
                 'HUNTER_SECRETS_FILE', 'HUNTER_PROJECT_TASK_SECRET', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'}
PROCESS_KEYS = {'HOME', 'PATH', 'USER', 'LOGNAME', 'SHELL', 'PWD', 'OLDPWD', 'TMPDIR', 'TMP', 'TEMP',
                'LANG', 'LC_ALL', 'TZ', 'ENV', 'BASH_ENV', 'SHELLOPTS', 'ZDOTDIR', 'CDPATH', 'IFS',
                'IKUN_ENV_FILE', 'HUNTER_PYTHON_BIN', 'IKUN_TRACKING_PYTHON', 'UV_THREADPOOL_SIZE',
                'NEXT_TELEMETRY_DISABLED', '__PYVENV_LAUNCHER__'}


def process_control(key):
    key = key.upper()
    return (key in PROCESS_KEYS or key.startswith(('PYTHON', 'DYLD_', 'LD_', 'LC_'))
            or (key.startswith('NODE_') and key not in ('NODE_ENV', 'NODE_OPTIONS')))


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inside(path, parent):
    path, parent = Path(path), Path(parent)
    require(path.is_absolute() and parent.is_absolute() and '..' not in path.parts
            and '..' not in parent.parts, 'OWNED_PATH_REQUIRED')
    require(not any(p.is_symlink() for p in (path, *path.parents, parent, *parent.parents)), 'ALIASED_PATH_REJECTED')
    normalized, boundary = path.resolve(), parent.resolve()
    require(boundary in normalized.parents, 'OWNED_PATH_REQUIRED')
    return normalized


def private_json(path):
    path = inside(Path(path), Path(path).parent)
    info = path.lstat()
    require(path.is_file() and not path.is_symlink() and info.st_nlink == 1 and info.st_mode & 0o777 == 0o600,
            'PRIVATE_JSON_REQUIRED')
    return json.loads(path.read_text())


def write_new(path, data):
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data if isinstance(data, bytes) else (json.dumps(data, indent=2) + '\n').encode())


def validate(plan, root=TARGET):
    worker = plan.get('worker')
    require(worker in DOMAINS, 'WORKER_REQUIRED')
    require(plan.get('accepted_frozen') is True, 'ACCEPTED_FREEZE_REQUIRED')
    for key in ('candidate_sha', 'source_commit', 'control_commit'):
        require(re.fullmatch('[a-f0-9]{40}', plan.get(key, '')) is not None, 'PINNED_SHA_REQUIRED')
    acceptance = inside(plan['acceptance_file'], root / 'config')
    require(sha(acceptance) == plan.get('acceptance_sha256'), 'FREEZE_RECEIPT_DRIFT')
    receipt = private_json(acceptance)
    require(receipt.get('accepted_frozen') is True and receipt.get('worker') == worker
            and all(receipt.get(key) == plan[key] for key in ('source_commit', 'control_commit')),
            'FREEZE_RECEIPT_MISMATCH')
    release = root / 'releases' / plan['candidate_sha']
    require(plan.get('release') == str(release), 'EXACT_RELEASE_REQUIRED')
    inside(release, root / 'releases')
    files = plan.get('runtime_sha256', {})
    require(bool(files) and files == receipt.get('runtime_sha256'), 'REVIEWED_RUNTIME_HASHES_REQUIRED')
    for relative, expected in files.items():
        path = Path(relative)
        require(not path.is_absolute() and '..' not in path.parts, 'INVALID_RUNTIME_PATH')
        require(relative.startswith('services/' + worker + '-worker/') or relative.startswith('schemas/' + worker + '/'),
                'OTHER_DOMAIN_RUNTIME_REJECTED')
        require(sha(inside(release / path, release)) == expected, 'RUNTIME_FILE_DRIFT')
    env_path = inside(plan['environment_file'], root / 'config')
    values = private_json(env_path)
    require(all(isinstance(k, str) and isinstance(v, str) for k, v in values.items()), 'STRING_ENV_REQUIRED')
    require(not any(process_control(k) for k in values), 'RESERVED_PROCESS_ENV_REJECTED')
    require(not any(k.upper() in PROVIDER_KEYS or k.startswith('NEXT_PUBLIC_') for k in values), 'PROVIDER_OR_PUBLIC_ENV_REJECTED')
    for value in values.values():
        if '://' in value:
            url = urlsplit(value)
            require(url.scheme == 'http' and url.hostname == '127.0.0.1' and not url.username
                    and not url.password and not url.query and not url.fragment, 'NONLOCAL_URL_REJECTED')
    data = root / 'data'
    require(values.get('DATA_ROOT') == str(data), 'DATA_ROOT_CHANGED')
    own_db = data / worker / (worker + '.db')
    identities = set()
    for name in ('auth', 'projects', 'hunter', 'tracking'):
        path = inside(data / name / (name + '.db'), data)
        if not path.exists():
            require(name != worker, 'EXPLICIT_MIGRATION_REQUIRED')
            continue
        info = path.stat()
        identity = (info.st_dev, info.st_ino)
        require(info.st_nlink == 1 and identity not in identities and info.st_mode & 0o777 == 0o600,
                'DATABASE_ALIAS_OR_PERMISSION')
        identities.add(identity)
    token = values.get(worker.upper() + '_API_TOKEN', '')
    require(32 <= len(token) <= 8192 and all(33 <= ord(c) <= 126 for c in token), 'DIRECTION_CREDENTIAL_REQUIRED')
    with closing(sqlite3.connect(own_db.as_uri() + '?mode=ro', uri=True, timeout=5)) as database:
        database.execute('PRAGMA query_only=ON')
        require(database.execute('PRAGMA integrity_check').fetchone() == ('ok',)
                and not database.execute('PRAGMA foreign_key_check').fetchall(), 'OWN_DATABASE_INTEGRITY')
        require(database.execute('PRAGMA user_version').fetchone()[0] == receipt.get('database_user_version')
                and database.execute('PRAGMA application_id').fetchone()[0] == receipt.get('database_application_id'),
                'EXPLICIT_MIGRATION_OR_DOMAIN_MISMATCH')
    if worker == 'hunter':
        require(values.get('HUNTER_EXTERNAL_IO_ENABLED') == '0' and values.get('HUNTER_HOST') == '127.0.0.1'
                and values.get('HUNTER_PORT') == str(DOMAINS[worker]) and values.get('HUNTER_DB') == str(own_db)
                and values.get('HUNTER_V2_MODE') == '1' and values.get('HUNTER_TENANT_ID') == 'ikun-main'
                and values.get('HUNTER_DELIVERY_PROTOCOL') == 'v2-event' and not values.get('HUNTER_VIEW_TOKEN')
                and values.get('HUNTER_ADMIN_TOKEN', token) == token,
                'HUNTER_OFF_MODE_REQUIRED')
    else:
        config_path = inside(values.get('IKUN_TRACKING_CONFIG', ''), root / 'config')
        config = private_json(config_path)
        require(config.get('remote_enabled') is False and config.get('dedicated_account') is False
                and config.get('host') == '127.0.0.1' and config.get('port') == DOMAINS[worker]
                and config.get('db_path') == str(own_db) and not config.get('token_file')
                and not config.get('service_token_file')
                and not config.get('admin_token_file') and not config.get('read_token_file')
                and not config.get('auth_session_url'), 'TRACKING_OFF_MODE_REQUIRED')
        require(sha(config_path) == receipt.get('tracking_config_sha256'), 'TRACKING_CONFIG_DRIFT')
    cwd = inside(plan['cwd'], root / 'jobs')
    require(cwd == root / 'jobs' / worker and cwd.is_dir(), 'OWNED_EMPTY_CWD_REQUIRED')
    directories = (cwd, release, release / 'services' / (worker + '-worker'),
                   release / 'services' / (worker + '-worker') / 'python')
    if worker == 'tracking':
        directories += (config_path.parent,)
    for directory in directories:
        require(not (directory / '.env').exists() and not (directory / '.env.local').exists(), 'IMPLICIT_DOTENV_REJECTED')
    argv = plan.get('argv', [])
    require(argv == receipt.get('argv') and argv and all(isinstance(x, str) and x for x in argv),
            'REVIEWED_ARGV_REQUIRED')
    require(not any(x in ('dev', '--reload', '--watch', 'init', 'migrate') for x in argv), 'START_MUST_NOT_MIGRATE')
    require(argv[0] in (str(root / 'toolchains/node24/bin/node'), str(root / 'venvs' / worker / 'bin/python')),
            'OWNED_EXECUTABLE_REQUIRED')
    if argv[0] == str(root / 'toolchains/node24/bin/node'):
        entry = 'services/' + worker + '-worker/dist/main.js'
        require(argv == [argv[0], str(release / entry)] and entry in files, 'EXACT_WORKER_ENTRY_REQUIRED')
        if worker == 'hunter':
            require(values.get('HUNTER_ENGINE') == 'python', 'REAL_ENGINE_ENTRY_REQUIRED')
        else:
            require('services/tracking-worker/python/entry.py' in files, 'TRACKING_PYTHON_ENTRY_REQUIRED')
    else:
        args = ['-m', 'hunterradar', 'run'] if worker == 'hunter' else ['-m', 'tracking.cli', 'serve', '--config', values['IKUN_TRACKING_CONFIG']]
        require(argv[1:] == args, 'EXACT_WORKER_ENTRY_REQUIRED')
    require(sha(argv[0]) == receipt.get('executable_sha256'), 'EXECUTABLE_DRIFT')
    clean = {'HOME': str(ACCOUNT_HOME), 'PATH': str(root / 'toolchains/node24/bin') + ':/usr/bin:/bin',
             'LANG': 'en_US.UTF-8', 'TZ': 'Asia/Shanghai', 'NODE_ENV': 'production',
             'NODE_OPTIONS': '--max-old-space-size=256', 'NEXT_TELEMETRY_DISABLED': '1',
             'UV_THREADPOOL_SIZE': '2', 'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
             'PYTHONNOUSERSITE': '1', 'PYTHONPATH': str(release / 'services' / (worker + '-worker') / 'python'),
             ('HUNTER_PYTHON_BIN' if worker == 'hunter' else 'IKUN_TRACKING_PYTHON'): str(root / 'venvs' / worker / 'bin/python')}
    clean.update(values)
    require(clean['NODE_ENV'] == 'production' and clean['NODE_OPTIONS'] == '--max-old-space-size=256', 'RESOURCE_MODE_CHANGED')
    return cwd, argv, clean


def render(plan, destination, root=TARGET):
    """Freeze-gated run wrapper is used even for an intentionally pending review plan."""
    worker = plan.get('worker')
    require(worker in DOMAINS, 'WORKER_REQUIRED')
    destination = inside(Path(destination), Path(destination).parent)
    require(not destination.exists() and destination.is_absolute(), 'NEW_PLAN_DIRECTORY_REQUIRED')
    if plan.get('accepted_frozen') is True:
        inside(destination, root / 'plans')
    destination.mkdir(mode=0o700)
    launcher = destination / 'night_worker_ops.py'
    write_new(launcher, Path(__file__).read_bytes())
    spec = destination / 'worker.json'
    write_new(spec, plan)
    label = 'ca.ikun.v2.c0lite.' + worker
    python = str(root / 'venv/bin/python')
    job = {'Label': label, 'ProgramArguments': [python, '-I', str(launcher), 'run', '--plan', str(spec)],
           'WorkingDirectory': str(root / 'jobs' / worker), 'RunAtLoad': True, 'KeepAlive': True,
           'ThrottleInterval': 30, 'ExitTimeOut': 30, 'Umask': 0o077, 'Nice': 5, 'ProcessType': 'Background',
           'StandardOutPath': str(root / 'logs' / (worker + '.log')),
           'StandardErrorPath': str(root / 'logs' / (worker + '.error.log'))}
    write_new(destination / (label + '.plist'), plistlib.dumps(job))
    write_new(destination / 'rollback.json', {'label': label, 'operation': 'bootout_owned_worker_only',
                                            'database_action': 'preserve', 'installed': False,
                                            'previous_worker_release': plan.get('previous_worker_release')})
    return {'label': label, 'installed': False, 'started': False,
            'status': 'RENDERED_PREFLIGHT_REQUIRED', 'plan': str(spec)}


def unload(plan_path, root=TARGET, agents=None, invoke=subprocess.run):
    """Rollback only the exact new owned job; archive its plist and preserve every DB."""
    plan_path = inside(Path(plan_path), root / 'plans')
    plan = private_json(plan_path)
    worker = plan.get('worker')
    require(worker in DOMAINS, 'WORKER_REQUIRED')
    label = 'ca.ikun.v2.c0lite.' + worker
    agents = Path(agents) if agents else ACCOUNT_HOME / 'Library/LaunchAgents'
    plist = agents / (label + '.plist')
    info = plist.lstat()
    require(not plist.is_symlink() and info.st_nlink == 1 and info.st_mode & 0o777 == 0o600, 'OWNED_PLIST_REQUIRED')
    raw = plist.read_bytes();job = plistlib.loads(raw)
    expected = [str(root / 'venv/bin/python'), '-I', str(plan_path.parent / 'night_worker_ops.py'), 'run', '--plan', str(plan_path)]
    require(job.get('Label') == label and job.get('ProgramArguments') == expected
            and job.get('WorkingDirectory') == str(root / 'jobs' / worker), 'OWNED_JOB_MISMATCH')
    target = 'gui/' + str(os.getuid()) + '/' + label
    def absent(result):
        output = result.stderr.decode(errors='replace') if isinstance(result.stderr, bytes) else result.stderr
        return result.returncode != 0 and 'Could not find service' in output and label in output
    current = invoke(['/bin/launchctl', 'print', target], capture_output=True, timeout=5)
    if current.returncode == 0:
        require(invoke(['/bin/launchctl', 'bootout', target], capture_output=True, timeout=30).returncode == 0,
                'OWNED_JOB_UNLOAD_FAILED')
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            current = invoke(['/bin/launchctl', 'print', target], capture_output=True, timeout=5)
            if absent(current):
                break
            require(current.returncode == 0, 'OWNED_JOB_STATUS_UNAVAILABLE')
            time.sleep(.2)
        else:
            raise ValueError('OWNED_JOB_STILL_RUNNING')
    else:
        require(absent(current), 'OWNED_JOB_STATUS_UNAVAILABLE')
    require(plist.read_bytes() == raw, 'OWNED_PLIST_CHANGED')
    parent = root / 'rollbacks' / (worker + '-' + uuid.uuid4().hex)
    inside(parent, root / 'rollbacks')
    parent.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.rename(plist, parent / plist.name)
    return {'status': 'OWNED_JOB_UNLOADED_AND_ARCHIVED', 'label': label, 'archive': str(parent),
            'database_action': 'preserved', 'other_jobs_changed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('render', 'check', 'run', 'unload'))
    parser.add_argument('--plan', required=True)
    parser.add_argument('--output')
    args = parser.parse_args()
    plan = private_json(args.plan)
    if args.command == 'unload':
        print(json.dumps(unload(args.plan)))
    elif args.command == 'render':
        require(args.output, 'OUTPUT_REQUIRED')
        print(json.dumps(render(plan, args.output)))
    else:
        cwd, argv, env = validate(plan)
        if args.command == 'check':
            print(json.dumps({'status': 'PASS_PREFLIGHT', 'worker': plan['worker'], 'configured_external_collection': False}))
        else:
            os.chdir(cwd)
            os.execve(argv[0], argv, env)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError):
        # Config values/argv may contain secrets: never include them or raw exception text.
        print(json.dumps({'status': 'BLOCKED_WORKER_PREFLIGHT'}), file=sys.stderr)
        sys.exit(2)
