"""Build output promotion for the protected v2 website only, without modifying worker jobs."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time
from deploy_v2_current import ROOT,V2,AGENTS,PYTHON,run,load,job,ready
from upgrade_v2_workers import unload
from v2_maintenance import backup,private,atomic

def main():
    os.umask(0o077)
    assert run(['git','branch','--show-current']).stdout.strip()=='codex/integration'
    assert not run(['git','status','--porcelain']).stdout.strip()
    sha=run(['git','rev-parse','HEAD']).stdout.strip()
    release=V2/'releases'/sha;release.mkdir(mode=0o700)
    archive=subprocess.check_output(['git','archive',sha],cwd=ROOT);subprocess.run(['/usr/bin/tar','-x','-C',str(release)],input=archive,check=True)
    for relative in ('node_modules','packages/contracts/dist','packages/contracts/node_modules','packages/runtime/dist','packages/runtime/node_modules','packages/ui/dist','packages/ui/node_modules','modules/auth/dist','apps/website/.next','apps/website/node_modules'):
        source=ROOT/relative
        if source.is_dir():shutil.copytree(source,release/relative,symlinks=True,ignore=shutil.ignore_patterns('cache') if relative.endswith('.next') else None)
    backup()
    destination=private(V2/'rollback'/('website-'+str(int(time.time()))))
    label='ca.ikun.v2.c0lite.web';path=AGENTS/(label+'.plist');before=path.read_bytes();(destination/path.name).write_bytes(before);(destination/path.name).chmod(0o600)
    env_path=V2/'config/web.environment.json';env_before=env_path.read_bytes();(destination/env_path.name).write_bytes(env_before);(destination/env_path.name).chmod(0o600)
    owner_path=V2/'owner.json';owner_before=owner_path.read_bytes();(destination/owner_path.name).write_bytes(owner_before)
    unload(label)
    try:
        env=json.loads(env_before);env['IKUN_RELEASE_SHA']=sha;atomic(env_path,env)
        load(job(label,[PYTHON,release/'release-integration/scripts/run_v2_web.py']));ready(4000)
        owner=json.loads(owner_before);owner['candidate_sha']=sha;atomic(owner_path,owner)
    except BaseException:
        unload(label);env_path.write_bytes(env_before);path.write_bytes(before);owner_path.write_bytes(owner_before);load(path);raise
    print('website updated',sha,'workers and Tunnel unchanged',flush=True)

if __name__=='__main__':os.chdir(ROOT);main()
