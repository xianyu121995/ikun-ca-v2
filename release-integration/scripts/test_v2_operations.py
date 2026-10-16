import importlib.util
import json
import sqlite3
import time
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

spec=importlib.util.spec_from_file_location('ops',Path(__file__).with_name('v2_maintenance.py'));ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)

def test_four_online_backups_and_retention(tmp_path):
    root=tmp_path/'v2';dest=tmp_path/'backups'
    for role in ops.ROLES:
        path=root/'data'/role/(role+'.db');path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as db:db.execute('CREATE TABLE sentinel(value)');db.execute('INSERT INTO sentinel VALUES(?)',(role,))
    now=datetime(2026,10,19,4,tzinfo=ZoneInfo('Asia/Shanghai'))
    for weeks in range(10,0,-1):ops.backup(root,dest,now-timedelta(weeks=weeks))
    result=ops.backup(root,dest,now)
    assert len(list((dest/'weekly').iterdir()))==8
    assert len(list((dest/'daily').iterdir()))==3
    for role in ops.ROLES:
        with sqlite3.connect(result/(role+'.db')) as db:assert db.execute('select value from sentinel').fetchone()[0]==role
        assert (result/(role+'.db')).stat().st_mode & 0o777==0o600

def test_log_rotation_does_not_replace_live_file(tmp_path):
    folder=tmp_path/'logs';folder.mkdir();path=folder/'web.log';path.write_bytes(b'x'*(11*1024*1024));inode=path.stat().st_ino
    now=time.time();ops.rotate(tmp_path,now)
    assert path.stat().st_ino==inode and path.stat().st_size==0
    archives=list(folder.glob('*.archive-*'));assert len(archives)==1
    ops.rotate(tmp_path,now+8*86400);assert not list(folder.glob('*.archive-*'))
