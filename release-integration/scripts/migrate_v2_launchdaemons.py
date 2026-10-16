#!/usr/bin/env python3
"""Move only the six owned v2 jobs to launchd's system domain, with rollback."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import shlex
import subprocess
import time
import urllib.request

HOME=Path('/Users/lvlei')
ACCOUNT=pwd.getpwnam('lvlei')
V2=HOME/'Library/Application Support/ikun-ca-v2-c0-lite'
AGENTS=HOME/'Library/LaunchAgents'
DAEMONS=Path('/Library/LaunchDaemons')
STAGES=V2/'ops/launchdaemons'
ROLES=('hunter','tracking-live','web','tunnel','health','backup')
PREFIX='ca.ikun.v2.c0lite.'
GUI='gui/'+str(ACCOUNT.pw_uid)


def call(*args):return subprocess.run(['/bin/launchctl',*map(str,args)],capture_output=True,text=True)
def private(path):path.mkdir(parents=True,exist_ok=True,mode=0o700);return path

def normalize(original):
    result=dict(original)
    assert result['Label'] in {PREFIX+r for r in ROLES}
    # Keep arguments and all provider/Tunnel configurations byte-for-byte unchanged.
    result.pop('LimitLoadToSessionType',None)
    result.pop('AssociatedBundleIdentifiers',None)
    result.update(UserName=ACCOUNT.pw_name,GroupName='staff',Umask=0o077,RunAtLoad=True)
    result['EnvironmentVariables']={**result.get('EnvironmentVariables',{}),'HOME':str(HOME),'TZ':'Asia/Shanghai'}
    return result

def prepare():
    assert os.getuid()==ACCOUNT.pw_uid
    stage=private(STAGES/('prepared-'+str(int(time.time()))))
    for role in ROLES:
        label=PREFIX+role;source=AGENTS/(label+'.plist')
        if (DAEMONS/source.name).exists() or call('print','system/'+label).returncode==0:
            raise RuntimeError('system_destination_already_exists:'+role)
        if call('print',GUI+'/'+label).returncode:raise RuntimeError('source_job_not_loaded:'+role)
        old=source.read_bytes();(stage/(role+'.agent.plist')).write_bytes(old)
        (stage/(role+'.daemon.plist')).write_bytes(plistlib.dumps(normalize(plistlib.loads(old))))
    for path in stage.iterdir():path.chmod(0o600)
    print('Prepared:',stage)
    print('Run on this Mac (password stays in Terminal):')
    print(shlex.join(['sudo','/usr/bin/python3','-I',str(Path(__file__).resolve()),'--install',str(stage)]))
    return stage

def unload(domain,label):
    info=call('print',domain+'/'+label)
    match=re.search(r'\bpid = (\d+)',info.stdout);pid=int(match[1]) if match else None
    result=call('bootout',domain+'/'+label)
    if result.returncode and not info.returncode:raise RuntimeError('unload_failed:'+label)
    for _ in range(150):
        loaded=call('print',domain+'/'+label).returncode==0
        alive=False
        if pid:
            try:os.kill(pid,0);alive=True
            except ProcessLookupError:pass
        if not loaded and not alive:return
        time.sleep(.2)
    raise RuntimeError('unload_timeout:'+label)

def wait_ready(role,domain="system"):
    urls={'web':'http://127.0.0.1:4000/health/ready','hunter':'http://127.0.0.1:4011/health/ready','tracking-live':'http://127.0.0.1:4012/health/ready','tunnel':'http://127.0.0.1:65520/ready'}
    if role not in urls:
        for _ in range(150):
            info=call('print',domain+'/'+PREFIX+role)
            if info.returncode:raise RuntimeError('system_schedule_missing:'+role)
            if not re.search(r'\bpid = (\d+)',info.stdout):
                match=re.search(r'last exit code = (\d+)',info.stdout)
                if match:
                    if int(match[1])!=0:raise RuntimeError('system_schedule_failed:'+role)
                    return
            time.sleep(.2)
        raise RuntimeError('system_schedule_not_completed:'+role)
    for _ in range(60):
        try:
            request=urllib.request.Request(urls[role],headers={'Host':'v2.ikun.ca'} if role=='web' else {})
            with urllib.request.urlopen(request,timeout=2) as response:
                if response.status==200:return
        except Exception:pass
        time.sleep(.5)
    raise RuntimeError('new_system_job_not_ready:'+role)

def install(stage):
    if os.geteuid()!=0:raise SystemExit('Administrator authorization required; use the prepared sudo command.')
    stage=stage.resolve()
    assert stage.parent==STAGES and not stage.is_symlink()
    if (stage/'installed.json').exists():raise RuntimeError('already_installed')
    # Finish all checks and a fresh four-store backup before the first stop.
    for role in ROLES:
        name=PREFIX+role+'.plist';old=(stage/(role+'.agent.plist')).read_bytes()
        assert (AGENTS/name).read_bytes()==old,'source_changed_reprepare'
        assert not (DAEMONS/name).exists(),'destination_exists'
        assert call('print','system/'+PREFIX+role).returncode!=0,'system_job_exists'
        assert plistlib.loads((stage/(role+'.daemon.plist')).read_bytes())==normalize(plistlib.loads(old))
    maintenance=Path(__file__).with_name('v2_maintenance.py')
    subprocess.run([str(V2/'venvs/tracking/bin/python'),str(maintenance),'backup'],check=True,user=ACCOUNT.pw_uid,group=ACCOUNT.pw_gid,extra_groups=os.getgrouplist(ACCOUNT.pw_name,ACCOUNT.pw_gid),env={'HOME':str(HOME),'PATH':'/usr/bin:/bin','TZ':'Asia/Shanghai'})
    changed=[]
    try:
        for role in ROLES:
            label=PREFIX+role;name=label+'.plist';destination=DAEMONS/name
            unload(GUI,label);changed.append(role)
            with destination.open('xb') as out:out.write((stage/(role+'.daemon.plist')).read_bytes())
            os.chown(destination,0,0);destination.chmod(0o644)
            result=call('bootstrap','system',destination)
            if result.returncode:raise RuntimeError('system_bootstrap_failed:'+role)
            wait_ready(role)
            result=call('disable',GUI+'/'+label)
            if result.returncode:raise RuntimeError('duplicate_agent_disable_failed:'+role)
            print(role+': system job ready',flush=True)
        installed=stage/'installed.json';installed.write_text(json.dumps({'installed_at':time.time(),'roles':list(ROLES),'databases_restored':False}));installed.chmod(0o600);os.chown(installed,ACCOUNT.pw_uid,ACCOUNT.pw_gid)
    except BaseException:
        failures=[]
        for role in reversed(changed):
            label=PREFIX+role;destination=DAEMONS/(label+'.plist')
            try:
                if call('print','system/'+label).returncode==0:unload('system',label)
                if destination.exists():destination.unlink()
                if call('enable',GUI+'/'+label).returncode:raise RuntimeError('enable_failed')
                if call('bootstrap',GUI,AGENTS/destination.name).returncode:raise RuntimeError('agent_bootstrap_failed')
                wait_ready(role,domain=GUI)
            except Exception:failures.append(role)
        if failures:print('Rollback needs attention:',','.join(failures),flush=True)
        else:print('Original v2 agents restored; databases and Tunnel configuration preserved.',flush=True)
        raise
    verify()

def verify():
    for role in ROLES:
        label=PREFIX+role;result=call('print','system/'+label)
        pid=re.search(r'\bpid = (\d+)',result.stdout)
        print(role,'system_loaded='+str(result.returncode==0),'pid='+str(pid[1] if pid else 'scheduled'))

if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--install',type=Path);g.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.prepare:prepare()
    elif a.install:install(a.install)
    else:verify()
