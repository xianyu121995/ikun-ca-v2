"""Synthetic isolated accounts through the accepted real TTY CLI; no password logging."""
import json
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[2]
NODE = Path('/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node')
PYTHON = ROOT / 'release-integration/.runtime/c0-lite/venv/bin/python'


def environment(data_root, origin):
    result = {k: os.environ[k] for k in ('HOME', 'LANG', 'TMPDIR') if k in os.environ}
    result.update(PATH=str(NODE.parent) + ':/usr/bin:/bin:/usr/sbin:/sbin', DATA_ROOT=str(data_root),
                  IKUN_AUTH_ORIGIN=origin, IKUN_AUTH_DEV='1', NODE_ENV='production')
    return result


def cli(data_root, origin, operation, username=None, password=None, expected=0):
    import pexpect
    args = [str(ROOT / 'modules/auth/dist/src/cli.js'), operation]
    if username:
        args += ['--username', username]
    process = pexpect.spawn(str(NODE), args, cwd=str(ROOT), env=environment(data_root, origin),
                            encoding='utf-8', echo=False, timeout=30)
    try:
        if password is not None:
            process.expect('初始密码（至少10字符）：')
            process.sendline(password)
            process.expect('再次输入密码：')
            process.sendline(password)
        process.expect(pexpect.EOF)
        process.close()
        if process.exitstatus != expected:
            raise RuntimeError('LOCAL_ACCOUNT_CLI_FAILED: ' + operation)
    finally:
        if process.isalive():
            process.close(force=True)


def provision(data_root, origin, output):
    data_root = Path(data_root)
    data_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    accounts = {}
    for key, name in [('admin', 'c0_admin'), ('user', 'c0_user'), ('forced', 'c0_forced')]:
        password = 'test-init1' if key == 'forced' else secrets.token_urlsafe(24)
        cli(data_root, origin, 'bootstrap' if key == 'admin' else 'create', name, password)
        accounts[key] = {'username': name, 'password': password}
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(accounts, stream)
    return accounts


def migrate_projects(data_root):
    env = environment(data_root, 'http://127.0.0.1:4000')
    result = subprocess.run([str(PYTHON), str(ROOT / 'modules/projects/integration/ipc-entry.py'), '--migrate',
                             '--database', str(Path(data_root) / 'projects/projects.db')],
                            env=env, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('EXPLICIT_PROJECTS_MIGRATION_FAILED')
