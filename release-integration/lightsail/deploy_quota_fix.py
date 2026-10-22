"""Approved staged quota repair; immutable release, verified backups, no provider calls."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expected', required=True)
    p.add_argument('--release', required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--final', action='store_true')
    args = p.parse_args()
    assert os.getuid() == 0
    os.umask(0o077)
    base = Path('/var/lib/ikun/production')
    old = Path('/opt/ikun/current').resolve()
    assert old.name == args.expected, 'unexpected_live_release'
    target = old.parent / args.release
    assert not target.exists(), 'release_already_exists'
    with tarfile.open(args.archive) as archive:
        members = archive.getmembers()
        assert all(not x.name.startswith('/') and '..' not in Path(x.name).parts
                   and not x.issym() and not x.islnk() for x in members), 'unsafe_overlay'
        assert members, 'empty_overlay'
        shutil.copytree(old, target, symlinks=True)
        archive.extractall(target, members=members)
    subprocess.run(['chown', '-R', 'ikun:ikun', str(target)], check=True)
    subprocess.run(['systemctl', 'start', 'ikun-backup.service'], check=True, timeout=180)
    manifest = max((base/'backups/daily').glob('*/verification.json'), key=lambda p:p.stat().st_mtime)
    report = json.loads(manifest.read_text())
    assert time.time()-manifest.stat().st_mtime < 180
    assert set(report['databases']) == {'auth', 'hunter', 'projects', 'tracking'}
    assert all(x['integrity']=='ok' and x['all_table_counts_match'] for x in report['databases'].values())
    print('VERIFIED_BACKUP', manifest.parent, flush=True)
    configs = {base/'config'/n: (base/'config'/n).read_bytes()
               for n in ('tracking.live.environment.json', 'hunter.live.environment.json', 'web.environment.json')}
    saved = base/'ops'/('quota-release-'+args.release)
    saved.mkdir(mode=0o700)
    for path, content in configs.items():
        (saved/path.name).write_bytes(content)
    def pid(unit):
        return subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip()
    untouched = ['ikun-projects', 'ikun-tunnel'] + ([] if args.final else ['ikun-web'])
    before = {u:pid(u) for u in untouched}
    lock = os.open(base/'data/.6551-watch.lock', os.O_RDWR|os.O_NOFOLLOW)
    stopped=[]; switched=False
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Avoid interrupting chargeable followings/AI requests. Never execute a recovery script.
        deadline=time.monotonic()+150
        while True:
            with sqlite3.connect((base/'data/hunter/hunter.db').as_uri()+'?mode=ro',uri=True) as db:
                states={k:json.loads(v) for k,v in db.execute("SELECT key,value FROM state WHERE key LIKE 'provider_intent:%' OR key LIKE 'ai_input:%'")}
            busy=any(k.startswith('provider_intent:followings:') and v=='in_flight' for k,v in states.items())
            busy=busy or any(k.startswith('ai_input:') and isinstance(v,dict) and 'profile' not in v
                             and time.time()-v.get('at',0)<40 for k,v in states.items())
            if not busy:break
            assert time.monotonic()<deadline, 'paid_request_still_in_flight'
            time.sleep(1)
        for unit in ('ikun-tracking-live','ikun-hunter'):
            subprocess.run(['systemctl','stop',unit],check=True,timeout=60);stopped.append(unit)
        for path, content in configs.items():
            d=json.loads(content)
            if args.final:
                d.pop('IKUN_6551_REST_PAUSED',None)
                d['IKUN_6551_LEDGER']=str(base/'ops/6551-ledger.sqlite3')
                d['IKUN_6551_DAILY_LIMIT']='300'
                d['IKUN_6551_BACKFILL_DAILY_LIMIT']='300'
            elif path.name!='web.environment.json':
                d['IKUN_6551_REST_PAUSED']='1'
            temp=path.with_suffix('.quota-stage')
            temp.write_text(json.dumps(d,indent=2)+'\n');temp.chmod(0o600)
            shutil.chown(temp,user='ikun',group='ikun');os.replace(temp,path)
        if args.final:
            import sys
            sys.path.insert(0,str(target/'packages/runtime/python'))
            from provider_6551 import Ledger
            ledger=Ledger(base/'ops/6551-ledger.sqlite3')
            ledger.trip_quota(initial=True)
            shutil.chown(ledger.path,user='ikun',group='ikun')
        link=Path('/opt/ikun/.current-quota-stage')
        link.symlink_to(target);os.replace(link,'/opt/ikun/current');switched=True
    except BaseException:
        if switched:
            link=Path('/opt/ikun/.current-quota-rollback');link.symlink_to(old);os.replace(link,'/opt/ikun/current')
        for path,content in configs.items():path.write_bytes(content)
        raise
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN);os.close(lock)
        for unit in stopped:subprocess.run(['systemctl','start',unit],check=True,timeout=45)
    if args.final:subprocess.run(['systemctl','restart','ikun-web'],check=True,timeout=60)
    assert all(pid(u)==v for u,v in before.items()), 'unrelated_service_restarted'
    print('RELEASE_ACTIVE',args.release,'REST_PAUSED' if not args.final else 'CIRCUIT_OPEN_NO_IMMEDIATE_PROBE',flush=True)


if __name__=='__main__':main()
