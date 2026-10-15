#!/usr/bin/env python3
"""Install only the explicitly approved NEW local C0-lite website, never a tunnel/DNS."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
TARGET=Path.home()/'Library/Application Support/ikun-ca-v2-c0-lite'
LABEL='ca.ikun.v2.c0lite.web'
NODE_SOURCE=Path('/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node')
MAIN='63e8a2857241c6a76226f21435e40db9736a1e7e'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def command(argv,**kwargs):
    result=subprocess.run([str(x) for x in argv],capture_output=True,text=True,timeout=kwargs.pop('timeout',60),**kwargs)
    if result.returncode:raise RuntimeError('COMMAND_FAILED: '+Path(str(argv[0])).name)
    return result.stdout.strip()


def write_private(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(value if isinstance(value,bytes) else (json.dumps(value,indent=2)+'\n').encode())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True)
    args=parser.parse_args()
    head=command(['git','rev-parse','HEAD'],cwd=ROOT)
    if head!=args.candidate or command(['git','branch','--show-current'],cwd=ROOT)!='codex/integration':
        raise RuntimeError('PINNED_INTEGRATION_CANDIDATE_REQUIRED')
    if command(['git','status','--porcelain'],cwd=ROOT) or command(['git','rev-parse','main'],cwd=ROOT)!=MAIN:
        raise RuntimeError('CLEAN_CANDIDATE_AND_UNCHANGED_MAIN_REQUIRED')
    binding=json.loads((ROOT/'release-integration/c0-lite/evidence/build-binding.json').read_text())
    for relative,expected in {**binding['sources'],**binding['compiled']}.items():
        if digest(ROOT/relative)!=expected:raise RuntimeError('TESTED_ARTIFACT_OR_SOURCE_DRIFT: '+relative)
    if TARGET.exists() or TARGET.is_symlink():raise RuntimeError('EXISTING_TARGET_PRESERVED')
    for parent in TARGET.parents:
        if parent.is_symlink():raise RuntimeError('RUNTIME_PARENT_ALIAS_REJECTED')
    plist=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    if plist.exists() or plist.is_symlink():raise RuntimeError('EXISTING_LABEL_FILE_PRESERVED')
    domain='gui/'+str(os.getuid())
    if subprocess.run(['/bin/launchctl','print',domain+'/'+LABEL],capture_output=True).returncode==0:
        raise RuntimeError('EXISTING_LABEL_PRESERVED')
    import socket
    port=None
    for number in (4000,4001,4002,4100):
        try:
            with socket.socket() as test:test.bind(('127.0.0.1',number))
            port=number;break
        except OSError:continue
    if port is None:raise RuntimeError('NO_NEW_FREE_LOOPBACK_PORT')
    report={'candidate_sha':head,'runtime_root':str(TARGET),'web_label':LABEL,'port':port,
            'hostname':'v2.ikun.ca','web_status':'PREPARING','public_status':'BLOCKED_ACCESS_NOT_CONFIGURED',
            'tunnel_created':False,'dns_changed':False,'old_services_changed':False,
            'created_at':datetime.now(timezone.utc).isoformat()}
    TARGET.mkdir(mode=0o700)
    write_private(TARGET/'owner.json',{'thread':'01a13c4c-039a-7713-98f4-47c694ed1a9e','candidate_sha':head,'labels':[LABEL,'ca.ikun.v2.c0lite.tunnel']})
    loaded=False
    try:
        release=TARGET/'releases'/head;release.mkdir(parents=True,mode=0o700)
        archive=subprocess.check_output(['git','archive',head],cwd=ROOT)
        subprocess.run(['/usr/bin/tar','-x','-C',str(release)],input=archive,check=True)
        # Inert preview fixtures are not part of the runtime artifact.
        for relative in ('modules/auth/integration/preview-only','packages/ui/preview','packages/ui/review'):
            path=release/relative
            if path.exists():shutil.rmtree(path)
        for relative in ('node_modules','packages/contracts/dist','packages/contracts/node_modules',
                         'packages/runtime/dist','packages/runtime/node_modules','packages/ui/dist','packages/ui/node_modules',
                         'modules/auth/dist','apps/website/.next','apps/website/node_modules'):
            source=ROOT/relative
            if not source.is_dir():
                if relative.endswith('/node_modules'):continue
                raise RuntimeError('REQUIRED_BUILD_ARTIFACT_MISSING')
            if relative.endswith('/.next'):
                shutil.copytree(source,release/relative,symlinks=True,ignore=lambda path,names:['cache'] if Path(path)==source and 'cache'in names else [])
            else:shutil.copytree(source,release/relative,symlinks=True)
        for path in release.rglob('*'):
            if path.is_symlink() and release not in path.resolve().parents:
                raise RuntimeError('CROSS_CHECKOUT_DEPENDENCY_REJECTED')
        node=TARGET/'toolchains/node24/bin/node';node.parent.mkdir(parents=True,mode=0o700)
        shutil.copyfile(NODE_SOURCE,node);node.chmod(0o700)
        if command([node,'--version'])!='v24.22.0':raise RuntimeError('PINNED_NODE_VERSION_REQUIRED')
        venv=TARGET/'venv'
        command(['/Users/lvlei/.local/bin/uv','venv','--python','/Users/lvlei/.local/bin/python3.11',venv])
        python=venv/'bin/python'
        command(['/Users/lvlei/.local/bin/uv','pip','install','--python',python,'-r',release/'release-integration/c0-lite/runtime-requirements.txt'],timeout=180)
        data=TARGET/'data';data.mkdir(mode=0o700)
        logs=TARGET/'logs';logs.mkdir(mode=0o700)
        config=TARGET/'config';config.mkdir(mode=0o700)
        env={'HOME':str(Path.home()),'PATH':str(node.parent)+':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
             'LANG':'en_US.UTF-8','TZ':'Asia/Shanghai','NODE_ENV':'production','NODE_OPTIONS':'--max-old-space-size=768',
             'NEXT_TELEMETRY_DISABLED':'1','DATA_ROOT':str(data),'IKUN_AUTH_ORIGIN':'https://v2.ikun.ca',
             'IKUN_AUTH_TENANT_ID':'ikun-main','PROJECTS_PYTHON':str(python),'PORT':str(port),'IKUN_RELEASE_SHA':head}
        command([node,release/'modules/auth/dist/src/cli.js','migrate'],env=env)
        command([python,release/'modules/projects/integration/ipc-entry.py','--migrate','--database',data/'projects/projects.db'],env=env)
        write_private(config/'cloudflare.local.json',{'owner_email':'','access_team':'','access_application_aud':'','tunnel_uuid':'',
                      'hostname':'v2.ikun.ca','tunnel_config':str(config/'cloudflared.yml'),'credentials_file':str(config/'tunnel.credentials.json')})
        write_private(config/'web.environment.json',env)
        artifact={'candidate_sha':head,'build_id':(release/'apps/website/.next/BUILD_ID').read_text().strip(),
                  'lock_sha256':digest(release/'pnpm-lock.yaml'),'node_sha256':digest(node),
                  'files':{str(p.relative_to(release)):digest(p) for p in (release/'apps/website/.next/server').rglob('*') if p.is_file()}}
        write_private(TARGET/'artifact.json',artifact)
        argv=['/usr/bin/env','-i',*[k+'='+v for k,v in env.items()],str(node),str(release/'scripts/start-c0-lite.mjs')]
        job={'Label':LABEL,'ProgramArguments':argv,'WorkingDirectory':str(release),'RunAtLoad':True,'KeepAlive':True,
             'ThrottleInterval':30,'ExitTimeOut':30,'Umask':0o077,'ProcessType':'Background','Nice':5,
             'StandardOutPath':str(logs/'web.log'),'StandardErrorPath':str(logs/'web.error.log')}
        write_private(plist,plistlib.dumps(job));command(['/usr/bin/plutil','-lint',plist])
        command(['/bin/launchctl','bootstrap',domain,plist]);loaded=True
        deadline=time.monotonic()+40;ready=False
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic()<deadline:
            try:
                with opener.open(f'http://127.0.0.1:{port}/health/ready',timeout=2) as response:
                    ready=response.status==200 and json.load(response)['data']['profile']=='c0-lite'
                if ready:break
            except (OSError,ValueError):pass
            time.sleep(.3)
        if not ready:raise RuntimeError('NEW_LOCAL_WEB_READINESS_FAILED')
        request=urllib.request.Request(f'http://127.0.0.1:{port}/login',headers={'Host':'v2.ikun.ca'})
        with opener.open(request,timeout=5) as response:
            if response.status!=200 or b'username' not in response.read():raise RuntimeError('NEW_REAL_LOGIN_PAGE_FAILED')
        report.update(web_status='RUNNING_LOCAL_ONLY',release=str(release),node=str(node),python=str(python),data_root=str(data),
                      build_id=artifact['build_id'],lock_sha256=artifact['lock_sha256'],artifact_sha256=digest(TARGET/'artifact.json'),
                      accounts='empty migrated auth.db; bootstrap must use local TTY',plist=str(plist))
    except Exception as error:
        report['web_status']='FAILED';report['error_type']=type(error).__name__
        report['reason']=str(error) if isinstance(error,RuntimeError) else 'new-runtime preparation failed; preserved for review'
        if loaded:
            subprocess.run(['/bin/launchctl','bootout',domain+'/'+LABEL],capture_output=True,timeout=40)
        raise
    finally:
        path=ROOT/'release-integration/.runtime/c0-lite/deployment.json'
        write_private(path,report)
        print(json.dumps({'receipt':str(path),'web_status':report['web_status'],'public_status':report['public_status']}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'BLOCKED','error_type':type(error).__name__,
                          'reason':str(error) if isinstance(error,RuntimeError) else 'new-runtime action failed'}),file=sys.stderr)
        sys.exit(2)
