"""Update only selected owned v2 workers, preserving their live private configurations."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import time
import urllib.request
from v2_maintenance import V2,backup,private

ROOT=Path(__file__).resolve().parents[2]
DOMAIN='gui/'+str(os.getuid())

def launch(*args):return subprocess.run(['/bin/launchctl',*map(str,args)],capture_output=True,text=True)
def unload(label):
    launch('bootout',DOMAIN+'/'+label)
    for _ in range(50):
        if launch('print',DOMAIN+'/'+label).returncode:return
        time.sleep(.2)
    raise RuntimeError('job_unload_timeout')

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('roles',nargs='+',choices=['hunter','tracking']);args=parser.parse_args()
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
    for role in args.roles:
        label='ca.ikun.v2.c0lite.'+('tracking-live' if role=='tracking' else 'hunter')
        if launch('print','system/'+label).returncode==0:raise RuntimeError('System daemon detected; use a privileged system-domain upgrade. No duplicate GUI job will be started.')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    release=V2/'worker-releases'/sha;release.mkdir(parents=True,mode=0o700)
    archive=subprocess.check_output(['git','archive',sha],cwd=ROOT);subprocess.run(['/usr/bin/tar','-x','-C',str(release)],input=archive,check=True)
    backup()
    rollback=private(V2/'rollback'/('workers-'+str(int(time.time()))))
    for role in args.roles:
        label='ca.ikun.v2.c0lite.'+('tracking-live' if role=='tracking' else 'hunter')
        path=Path.home()/'Library/LaunchAgents'/(label+'.plist');old=path.read_bytes();(rollback/path.name).write_bytes(old);(rollback/path.name).chmod(0o600)
        job=plistlib.loads(old);job['ProgramArguments'][1]=str(release/'release-integration/scripts/run_v2_worker.py')
        unload(label)
        try:
            path.write_bytes(plistlib.dumps(job));path.chmod(0o600)
            result=launch('bootstrap',DOMAIN,path)
            if result.returncode:raise RuntimeError('job_bootstrap_failed')
            port=4011 if role=='hunter' else 4012
            for attempt in range(40):
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health/ready',timeout=2) as response:
                        if response.status==200:break
                except Exception:pass
                time.sleep(.5)
            else:raise RuntimeError('worker_not_ready')
        except BaseException:
            unload(label);path.write_bytes(old)
            result=launch('bootstrap',DOMAIN,path)
            if result.returncode:raise RuntimeError('rollback_bootstrap_failed')
            raise
        print(role,'updated',sha,flush=True)

if __name__=='__main__':main()
