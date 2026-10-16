#!/usr/bin/env python3
"""Authorized v2-only release. Preserve old configurations and four databases."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from v2_maintenance import backup,private,atomic,V2,BACKUPS

ROOT=Path(__file__).resolve().parents[2]
DOMAIN='gui/'+str(os.getuid())
AGENTS=Path.home()/'Library/LaunchAgents'
PYTHON=V2/'venvs/tracking/bin/python'

def run(args,check=True):return subprocess.run([str(x) for x in args],check=check,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
def stop(label):
    run(['/bin/launchctl','bootout',DOMAIN+'/'+label],False)
def load(path):
    label=plistlib.loads(path.read_bytes())['Label']
    run(['/bin/launchctl','enable',DOMAIN+'/'+label]);run(['/bin/launchctl','bootstrap',DOMAIN,path])
def ready(port):
    for _ in range(40):
        try:
            request=urllib.request.Request(f'http://127.0.0.1:{port}/health/ready',headers={'Host':'v2.ikun.ca'})
            with urllib.request.urlopen(request,timeout=2) as response:
                if response.status==200:return
        except Exception:pass
        time.sleep(.5)
    raise RuntimeError('service_not_ready:'+str(port))
def job(label,args,*,interval=None,calendar=None):
    value={'Label':label,'ProgramArguments':[str(x) for x in args],'WorkingDirectory':str(V2),'RunAtLoad':True,'ProcessType':'Background','Nice':5,'StandardOutPath':str(V2/'logs'/(label+'.log')),'StandardErrorPath':str(V2/'logs'/(label+'.error.log')),'EnvironmentVariables':{'HOME':str(Path.home()),'PATH':'/usr/bin:/bin','TZ':'Asia/Shanghai','LANG':'en_US.UTF-8'}}
    if interval:value['StartInterval']=interval
    elif calendar:value['StartCalendarInterval']=calendar
    else:value.update(KeepAlive=True,ThrottleInterval=30)
    for name in ('StandardOutPath','StandardErrorPath'):
        log=Path(value[name]);fd=os.open(log,os.O_CREAT|os.O_APPEND|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(fd);log.chmod(0o600)
    path=AGENTS/(label+'.plist');path.write_bytes(plistlib.dumps(value));path.chmod(0o600)
    return path

def activate_hunters(release):
    sys.path[:0]=[str(release/'services/hunter-worker/python'),str(release/'packages/runtime/python')]
    from hunterradar.store import Store
    source=json.loads((ROOT.parent/'hunter-worker/var/directory-v2-final-8f5a453a/directory-package-v2-for-root-review.json').read_text())['rows']['hunters']
    expected={r['username'].lower():r for r in source}
    store=Store(V2/'data/hunter/hunter.db')
    actual={r['username']:r for r in store.hunters()}
    assert len(expected)==88 and all(name in actual for name in expected)
    for name,item in expected.items():
        row=store.hunter(actual[name]['id'])
        if row['profile_status']!='ready':row=store.adopt_legacy_profile(row['id'],row['version'],item)
        if not row['enabled']:row=store.patch(row['id'],row['version'],enabled=True,actor='owner-approved-activation')
        row=store.hunter(row['id']);assert row['mode']==item['monitor_mode']
        if name in ('0xbadkoi','captainqygi'):
            store.set_state('approved_flag:'+row['id'],{'id':{'0xbadkoi':'1318746','captainqygi':'1318675'}[name]})
    for name in ('c0fhunter1','c0fhunter2'):
        row=store.hunter(actual[name]['id'])
        if row['enabled']:store.patch(row['id'],row['version'],enabled=False,actor='owner-approved-test-disable')
    print('88 hunters activated with original profiles; two fixtures disabled',flush=True)

def main():
    os.umask(0o077)
    for role in ('web','hunter','tracking-live','tunnel'):
        if run(['/bin/launchctl','print','system/ca.ikun.v2.c0lite.'+role],check=False).returncode==0:raise RuntimeError('System daemon detected; use a privileged system-domain upgrade. No duplicate GUI job will be started.')
    assert run(['git','branch','--show-current']).stdout.strip()=='codex/integration'
    assert not run(['git','status','--porcelain']).stdout.strip()
    assert run(['git','rev-parse','main']).stdout.strip()=='63e8a2857241c6a76226f21435e40db9736a1e7e'
    sha=run(['git','rev-parse','HEAD']).stdout.strip()
    release=V2/'releases'/sha
    assert not release.exists(), 'new release only'
    release.mkdir(mode=0o700)
    archive=subprocess.check_output(['git','archive',sha],cwd=ROOT)
    subprocess.run(['/usr/bin/tar','-x','-C',str(release)],input=archive,check=True)
    for relative in ('node_modules','packages/contracts/dist','packages/contracts/node_modules','packages/runtime/dist','packages/runtime/node_modules','packages/ui/dist','packages/ui/node_modules','modules/auth/dist','apps/website/.next','apps/website/node_modules'):
        src=ROOT/relative
        if src.is_dir():shutil.copytree(src,release/relative,symlinks=True,ignore=shutil.ignore_patterns('cache') if relative.endswith('.next') else None)
    snapshot=backup();print('four database online backup completed',flush=True)
    rollback=private(V2/'rollback'/('owner-'+datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S')))
    shutil.copytree(V2/'config',rollback/'config')
    if (V2/'owner.json').exists():shutil.copy2(V2/'owner.json',rollback/'owner.json')
    private(rollback/'agents')
    old_labels=('ca.ikun.v2.c0lite.web','ca.ikun.v2.c0lite.hunter','ca.ikun.v2.c0lite.tracking-test')
    for label in old_labels:
        shutil.copy2(AGENTS/(label+'.plist'),rollback/'agents'/(label+'.plist'))
    # No Tunnel plist, account, DNS or legacy service mutation.
    web=json.loads((V2/'config/web.environment.json').read_text());web['IKUN_RELEASE_SHA']=sha;web.pop('IKUN_TRACKING_FIXTURE',None)
    hunter=json.loads((V2/'config/hunter.environment.json').read_text())
    values={}
    for line in (Path.home()/'Documents/ChatGPT/猎手/.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=line.split('=',1);values[key.strip()]=value.strip().strip('\"\'')
    token=json.loads((V2/'target-test/config/provider.environment.private.json').read_text())['IKUN_TRACKING_6551_TOKEN']
    assert values['TWITTER_API_TOKEN']==token, 'provider account mismatch'
    assert values.get('TWITTERAPI_IO_API_KEY'), 'REST key missing'
    hunter.update(OPENNEWS_TOKEN=token,TWITTERAPI_IO_API_KEY=values['TWITTERAPI_IO_API_KEY'],HUNTER_EXTERNAL_IO_ENABLED='1',HUNTER_REQUIRE_EXTERNAL_IO_DISABLED='0',HUNTER_PROJECT_DELIVERY_ENABLED='1',HUNTER_PROJECT_TASK_URL='http://127.0.0.1:4000/internal/v1/ingest/hunter',HUNTER_TWITTERAPI_DAILY_CREDITS='100000')
    tracking={'DATA_ROOT':web['DATA_ROOT'],'TRACKING_API_TOKEN':web['TRACKING_API_TOKEN'],'IKUN_TRACKING_6551_TOKEN':token,'IKUN_TRACKING_CONFIG':str(V2/'config/tracking.live.json')}
    cfg={'db_path':str(V2/'data/tracking/tracking.db'),'remote_enabled':True,'shared_account_safe':True,'dedicated_account':False,'watch_group':'ikun-ca-v2-project-tracking','host':'127.0.0.1','port':4012,'heartbeat_seconds':3,'reconcile_seconds':10,'remote_fresh_seconds':660,'backfill_seconds':300,'adopted_watch_ids':{'0x2a_ikun':'1322757'}}
    if (V2/'config/tracking.live.json').exists():cfg['adopted_watch_ids'].update(json.loads((V2/'config/tracking.live.json').read_text()).get('adopted_watch_ids') or {})
    atomic(V2/'config/hunter.live.environment.json',hunter);atomic(V2/'config/tracking.live.environment.json',tracking);atomic(V2/'config/tracking.live.json',cfg)
    new_tracking='ca.ikun.v2.c0lite.tracking-live'
    changed=False
    try:
        for label in old_labels:stop(label)
        time.sleep(3)
        changed=True
        activate_hunters(release)
        atomic(V2/'config/web.environment.json',web)
        paths=[job('ca.ikun.v2.c0lite.hunter',[V2/'venvs/hunter/bin/python',release/'release-integration/scripts/run_v2_worker.py','hunter']),job(new_tracking,[PYTHON,release/'release-integration/scripts/run_v2_worker.py','tracking']),job('ca.ikun.v2.c0lite.web',[PYTHON,release/'release-integration/scripts/run_v2_web.py'])]
        for path in paths:load(path)
        for port in (4000,4011,4012):ready(port)
        for label in ('ca.ikun.v2.c0lite.tracking-test','ca.ikun.v2.c0lite.tracking'):
            run(['/bin/launchctl','disable',DOMAIN+'/'+label])
        owner=json.loads((V2/'owner.json').read_text());owner['candidate_sha']=sha;atomic(V2/'owner.json',owner)
        # launchd uses the Mac's verified Asia/Shanghai system timezone.
        maintenance=release/'release-integration/scripts/v2_maintenance.py'
        for label,action,options in [('ca.ikun.v2.c0lite.health','health',{'interval':300}),('ca.ikun.v2.c0lite.backup','backup',{'calendar':{'Hour':4,'Minute':0}})]:
            stop(label);load(job(label,[PYTHON,maintenance,action],**options))
        print('v2 deployed:',sha,'rollback:',rollback,flush=True)
    except BaseException:
        for label in ('ca.ikun.v2.c0lite.web','ca.ikun.v2.c0lite.hunter',new_tracking):stop(label)
        for name in ('web.environment.json',):shutil.copy2(rollback/'config'/name,V2/'config'/name)
        if (rollback/'owner.json').exists():shutil.copy2(rollback/'owner.json',V2/'owner.json')
        for label in old_labels:
            path=AGENTS/(label+'.plist');shutil.copy2(rollback/'agents'/path.name,path);load(path)
        print('v2 jobs/config rolled back; databases preserved',flush=True)
        raise

if __name__=='__main__':
    os.chdir(ROOT)
    main()
