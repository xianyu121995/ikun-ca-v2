"""Linux-only isolated migration rehearsal; no Mac paths or live credentials."""
import json,os,sys
from pathlib import Path
role=sys.argv[1]
config=Path('/var/lib/ikun/test/config/environment.json')
if config.stat().st_mode&0o077:raise SystemExit('PRIVATE_CONFIG_REQUIRED')
env=os.environ.copy();env.update(json.loads(config.read_text()))
root=Path('/opt/ikun/current').resolve();env.update(HOME='/var/lib/ikun',TZ='Asia/Shanghai',NODE_ENV='production',NEXT_TELEMETRY_DISABLED='1',PATH='/opt/ikun/toolchains/node24/bin:/usr/local/bin:/usr/bin:/bin')
if role=='web':
 os.chdir(root/'apps/website');env['NODE_OPTIONS']='--max-old-space-size=768'
 os.execve('/opt/ikun/toolchains/node24/bin/node',['node',str(root/'apps/website/node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port','4000'],env)
elif role=='projects':
 os.chdir(root/'modules/projects/candidate')
 os.execve('/opt/ikun/venvs/projects/bin/python',['/opt/ikun/venvs/projects/bin/python',str(root/'modules/projects/integration/ipc-entry.py')],env)
elif role in ('hunter','tracking'):
 # This fence is deliberately absent throughout the first three migration steps.
 if not Path('/etc/ikun/ENABLE_EXTERNAL_MONITORING').is_file():raise SystemExit('EXTERNAL_MONITORING_NOT_APPROVED')
 env['PYTHONPATH']=str(root/'packages/runtime/python')+':'+str(root/('services/'+role+'-worker/python'))
 os.chdir(root)
 args=['/opt/ikun/venvs/'+role+'/bin/python','-m','hunterradar','run'] if role=='hunter' else ['/opt/ikun/venvs/'+role+'/bin/python','-m','tracking.cli','serve','--config',str(config.parent/'tracking.json')]
 os.execve('/opt/ikun/venvs/'+role+'/bin/python',args,env)
else:raise SystemExit('UNKNOWN_ROLE')
