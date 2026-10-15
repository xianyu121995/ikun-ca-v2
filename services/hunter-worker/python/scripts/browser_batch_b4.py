"""Foreground fixture lifecycle, to be wrapped by the one shared heavy lock."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import uuid

from hunterradar.store import Store
from hunterradar.parsers import Follow,Target

MODULE=Path(__file__).resolve().parents[1]
PREVIEW=MODULE/'var/b4/preview'
parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['formal','legacy']);args=parser.parse_args()
folder=MODULE/'var/b4'/('browser-'+args.mode+'-'+str(uuid.uuid4()));folder.mkdir(parents=True,mode=0o700)
evidence=MODULE/'docs/b4'/('browser' if args.mode=='formal' else 'legacy-browser');evidence.mkdir(parents=True,exist_ok=True)
failures=[evidence/name for name in ('failure.json','failure.png') if (evidence/name).exists()]
if failures:
 archive=evidence/('attempt-'+str(uuid.uuid4()));archive.mkdir()
 for old in failures:shutil.move(str(old),str(archive/old.name))
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
web_port,hunter_port=port(),port()
while web_port==hunter_port:hunter_port=port()
data=folder/'data';data.mkdir(mode=0o700)
node=Path(os.environ['B4_NODE'])
env={key:os.environ[key] for key in ('PATH','HOME','TMPDIR','LANG','SHELL') if key in os.environ}
env.update(PYTHONPATH=str(MODULE),NEXT_TELEMETRY_DISABLED='1',DATA_ROOT=str(data),HUNTER_DB=str(data/'hunter/hunter.db'),
 HUNTER_V2_MODE='1',HUNTER_API_TOKEN=secrets.token_urlsafe(32),HUNTER_HOST='127.0.0.1',HUNTER_PORT=str(hunter_port),
 HUNTER_EXTERNAL_IO_ENABLED='0',HUNTER_PROJECT_DELIVERY_ENABLED='0',IKUN_HUNTER_ORIGIN=f'http://127.0.0.1:{hunter_port}',
 HUNTER_DELIVERY_PROTOCOL='v2-event',
 IKUN_AUTH_ORIGIN=f'http://127.0.0.1:{web_port}',IKUN_AUTH_DEV='1',B4_PREVIEW_ROOT=str(PREVIEW),B4_BROWSER_EVIDENCE=str(evidence),
 B4_NODE=str(node),HUNTER_PLAYWRIGHT_MODULE=os.environ['HUNTER_PLAYWRIGHT_MODULE'],BROWSER_CHANNEL='chrome')
children=[];logs=[]
def spawn(command,cwd,name):
 log=(folder/(name+'.log')).open('w');logs.append(log)
 child=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT);children.append(child);return child
def ready(child,url):
 for _ in range(160):
  if child.poll() is not None:raise RuntimeError('fixture exited: '+url)
  try:
   with urlopen(url,timeout=1) as response:
    if response.status==200:return
  except Exception:pass
  time.sleep(.15)
 raise RuntimeError('fixture readiness deadline: '+url)
try:
 if args.mode=='formal':
  subprocess.run([str(node),str(MODULE/'integration/tests/provision-browser.mjs')],env=env,check=True)
  store=Store(Path(env['HUNTER_DB']),initialize=True);now=round(time.time(),3)
  for i in (1,2):
   row=store.add('fixture_hunter'+str(i),now=now-1000)
   store.apply_profile(row,str(100+i),'Fixture Hunter',5000,now-1000)
   row=store.hunter(row['id']);store.establish_wss_baseline([row],now-1000)
   for j in range(112):
    target=Target('fixture_p'+str(j),str(1000+j),'B4 Fixture Project '+str(j),'合成夹具资料 · 非真实平台')
    store.ingest_wss(Follow(row['username'],target,now-500+j,now,'6551_WSS',f'fixture-{i}-{j}'))
   store.patch(row['id'],store.hunter(row['id'])['version'],enabled=False)
  hunter=spawn([sys.executable,'-m','hunterradar','run'],folder,'hunter');ready(hunter,env['IKUN_HUNTER_ORIGIN']+'/health/ready')
  web=spawn([str(node),str(PREVIEW/'apps/website/node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',str(web_port)],PREVIEW/'apps/website','next')
  ready(web,env['IKUN_AUTH_ORIGIN']+'/login')
  subprocess.run([str(node),str(MODULE/'integration/tests/browser.cjs')],env=env,cwd=MODULE,check=True)
 else:
  env.update(HUNTER_FIXTURE_DB=str(data/'hunter/hunter.db'),HUNTER_FIXTURE_PORT=str(hunter_port),HUNTER_TEST_URL=f'http://127.0.0.1:{hunter_port}',HUNTER_BROWSER_EVIDENCE=str(evidence))
  child=spawn([sys.executable,str(MODULE/'scripts/preview_fixture.py')],folder,'legacy');ready(child,env['HUNTER_TEST_URL']+'/hunterradar')
  subprocess.run([str(node),str(MODULE/'tests/browser.cjs')],env=env,cwd=MODULE,check=True)
 print('B4_BROWSER_BATCH_PASS '+args.mode)
finally:
 for child in reversed(children):
  if child.poll() is None:
   child.terminate()
   try:child.wait(timeout=15)
   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
 for log in logs:log.close()
