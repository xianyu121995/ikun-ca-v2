"""Stop only the six approved Mac jobs, retain definitions/data, and snapshot for handover."""
import json
import os
import plistlib
import pwd
import re
import socket
import shutil
import subprocess
import sys
import time
from pathlib import Path

assert os.geteuid() == 0, 'administrator_required'
account = pwd.getpwnam('lvlei')
home = Path(account.pw_dir)
base = home/'Library/Application Support/ikun-ca-v2-c0-lite'
stage = base/'ops/lightsail-cutover'
stage.mkdir(mode=0o700, exist_ok=True)
os.chown(stage, account.pw_uid, account.pw_gid)
roles = ('health', 'backup', 'web', 'hunter', 'tracking-live', 'tunnel')
prefix = 'ca.ikun.v2.c0lite.'
python = base/'venvs/tracking/bin/python'
helper = Path(__file__).with_name('verified_backup.py')


def user(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, user=account.pw_uid,
                          group=account.pw_gid, extra_groups=os.getgrouplist(account.pw_name, account.pw_gid),
                          env={'HOME': str(home), 'PATH': '/usr/bin:/bin', 'TZ': 'Asia/Shanghai'}, **kwargs)


def launch(*args):
    return subprocess.run(['/bin/launchctl', *args], capture_output=True, text=True)


def snapshot():
    result = user([python, helper, '--root', base/'data', '--destination',
                   base/'ops/lightsail-snapshots'], capture_output=True, text=True)
    print(result.stdout, end='', flush=True)
    match = re.search(r'^VERIFIED_BACKUP (.+)$', result.stdout, re.M)
    assert match, 'verified_backup_not_published'
    return match[1]


def install_pull_schedule():
    script = stage/'pull_server_backup.py'
    shutil.copyfile(Path(__file__).with_name('pull_server_backup.py'), script)
    script.chmod(0o600)
    os.chown(script, account.pw_uid, account.pw_gid)
    label = 'ca.ikun.lightsail.backup-pull'
    path = Path('/Library/LaunchDaemons')/(label+'.plist')
    assert not path.exists(), 'backup_pull_already_configured'
    job = {'Label': label, 'UserName': account.pw_name, 'GroupName': 'staff', 'Umask': 0o077,
           'ProgramArguments': [str(python), str(script)], 'RunAtLoad': False,
           'StartCalendarInterval': {'Hour': 4, 'Minute': 30},
           'EnvironmentVariables': {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'TZ': 'Asia/Shanghai'},
           'StandardOutPath': str(stage/'backup-pull.log'),
           'StandardErrorPath': str(stage/'backup-pull.error.log')}
    for name in ('StandardOutPath', 'StandardErrorPath'):
        p = Path(job[name])
        p.touch(mode=0o600, exist_ok=True)
        os.chown(p, account.pw_uid, account.pw_gid)
    path.write_bytes(plistlib.dumps(job))
    path.chmod(0o644)
    os.chown(path, 0, 0)
    assert launch('bootstrap', 'system', str(path)).returncode == 0, 'backup_pull_install_failed'
    print('MAC_DAILY_SERVER_BACKUP_PULL_SCHEDULED_0430_BEIJING', flush=True)


if sys.argv[1] == 'stop':
    assert not (stage/'mac-stopped.json').exists(), 'already_stopped'
    first = snapshot()
    for role in roles:
        label = prefix+role
        path = Path('/Library/LaunchDaemons')/(label+'.plist')
        job = plistlib.loads(path.read_bytes())
        assert job['Label'] == label
        (stage/path.name).write_bytes(path.read_bytes())
        (stage/path.name).chmod(0o600)
    # Do not interrupt an unfinished paid REST request. Never clear a billing fence.
    probe = '''import sqlite3,json,sys
from pathlib import Path
p=Path.home()/'Library/Application Support/ikun-ca-v2-c0-lite/data/hunter/hunter.db'
with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as c:
 n=sum(json.loads(v)=='in_flight' for k,v in c.execute("select key,value from state where key like 'provider_intent:%'"))
print(n)
'''
    for _ in range(90):
        n = int(user([python, '-c', probe], capture_output=True, text=True).stdout.strip())
        if n == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('paid_request_in_flight_no_jobs_stopped')
    for role in roles:
        label = prefix+role
        before = launch('print', 'system/'+label)
        pid = re.search(r'\bpid = (\d+)', before.stdout)
        result = launch('disable', 'system/'+label)
        assert result.returncode == 0, 'job_disable_failed:'+role
        if before.returncode == 0:
            assert launch('bootout', 'system/'+label).returncode == 0, 'job_stop_failed:'+role
        for _ in range(120):
            alive = False
            if pid:
                try:
                    os.kill(int(pid[1]), 0)
                    alive = True
                except ProcessLookupError:
                    pass
            if not alive and launch('print', 'system/'+label).returncode != 0:
                break
            time.sleep(.25)
        else:
            raise RuntimeError('job_still_running:'+role)
        print('MAC_STOPPED', role, flush=True)
    for port in (4000, 4011, 4012, 65520):
        for _ in range(40):
            with socket.socket() as probe_socket:
                probe_socket.settimeout(.2)
                closed = probe_socket.connect_ex(('127.0.0.1', port)) != 0
            if closed:
                break
            time.sleep(.25)
        else:
            raise RuntimeError('mac_port_still_open:' + str(port))
    last = snapshot()
    record = stage/'mac-stopped.json'
    record.write_text(json.dumps({'stopped_at': time.time(), 'prestop_backup': first,
                                 'final_backup': last, 'roles': roles, 'data_deleted': False}))
    record.chmod(0o600)
    os.chown(record, account.pw_uid, account.pw_gid)
    install_pull_schedule()
    print('MAC_HANDOVER_READY', last, flush=True)
elif sys.argv[1] == 'restore':
    # Operator must first stop all server jobs and its tunnel; never activate both sides.
    assert (stage/'mac-stopped.json').exists(), 'no_completed_handover'
    for role in ('web', 'hunter', 'tracking-live', 'tunnel', 'health', 'backup'):
        label = prefix+role
        assert launch('enable', 'system/'+label).returncode == 0
        path = Path('/Library/LaunchDaemons')/(label+'.plist')
        assert launch('bootstrap', 'system', str(path)).returncode == 0
        print('MAC_RESTORED', role, flush=True)
else:
    raise SystemExit('unknown_action')
