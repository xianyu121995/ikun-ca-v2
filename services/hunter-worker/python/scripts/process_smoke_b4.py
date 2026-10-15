"""Run only after the C0 priority hold is lifted, under the shared heavy lock."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import Request,urlopen
import uuid

from hunterradar.store import Store
from hunterradar.parsers import Follow,Target
from hunterradar.formal import FormalService

MODULE=Path(__file__).resolve().parents[1]
ROOT=MODULE.parents[2]
NODE=Path(os.environ['B4_NODE'])
folder=MODULE/'var/b4'/('process-'+str(uuid.uuid4()));folder.mkdir(parents=True,mode=0o700)
database=folder/'hunter'/'hunter.db'
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
token=secrets.token_urlsafe(32)
env={'PATH':os.environ['PATH'],'PYTHONPATH':str(MODULE),'PYTHONUNBUFFERED':'1','HUNTER_DB':str(database),'HUNTER_HOST':'127.0.0.1','HUNTER_PORT':str(port),
 'DATA_ROOT':str(folder),'HUNTER_ENGINE':'python','HUNTER_PYTHON_BIN':sys.executable,
 'HUNTER_V2_MODE':'1','HUNTER_API_TOKEN':token,'HUNTER_TENANT_ID':'ikun-main','HUNTER_EXTERNAL_IO_ENABLED':'0','HUNTER_PROJECT_DELIVERY_ENABLED':'0','HUNTER_DELIVERY_PROTOCOL':'v2-event'}
principal=json.dumps({'user_id':'fixture-admin','tenant_id':'ikun-main','role':'superadmin'})
def call(path,body=None,*,method=None,extra=None):
    request=Request(f'http://127.0.0.1:{port}'+path,data=json.dumps(body).encode() if body is not None else None,
        method=method,headers={'authorization':'Bearer '+token,'x-ikun-principal':principal,'content-type':'application/json','idempotency-key':str(uuid.uuid4()),**(extra or {})})
    with urlopen(request,timeout=2) as response:return json.load(response)['data']
def start():
    process=subprocess.Popen([str(NODE),str(ROOT/'services/hunter-worker/dist/main.js')],cwd=folder,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('fixture_process_start_failed')
            try:
                state=call('/internal/v1/status')
                if state['worker_alive']:return process
            except Exception:pass
            time.sleep(.1)
        raise RuntimeError('fixture_start_deadline')
    except BaseException:
        if process.poll() is None:process.terminate();process.wait(timeout=15)
        raise
process=None
try:
    subprocess.run([sys.executable,'-m','hunterradar','init'],cwd=folder,env=env,check=True,capture_output=True)
    fixture=Store(database);now=round(time.time(),3)
    for index in (1,2):
        row=fixture.add('os_fixture'+str(index),now=now-100)
        fixture.apply_profile(row,str(100+index),'Synthetic',5000,now-100)
        row=fixture.hunter(row['id']);fixture.establish_wss_baseline([row],now-100)
        fixture.ingest_wss(Follow(row['username'],Target('os_target','999','OS Fixture','Synthetic only'),now,now,'6551_WSS','os-'+str(index)))
        fixture.patch(row['id'],row['version'],enabled=False)
    identifier=fixture.discoveries(now=now)[0]['discovery_id'];path='/api/v1/hunter/discoveries/'+identifier
    process=start();pids=[process.pid]
    created=call('/api/v1/hunter/accounts',{'x_handle':'fixture_hunter','label':'fixture','notes':'restart test','enabled':False})
    dto=call(path);patch_key=str(uuid.uuid4());patch_headers={'if-match':f'"rev-{dto["revision"]}"','idempotency-key':patch_key}
    patch=call(path,{'notes':'OS persistent research'},method='PATCH',extra=patch_headers)
    dto=call(path);command=call(path+'/monitoring-requests',{'confirmed':True,'project':dto['project']},extra={'if-match':f'"rev-{dto["revision"]}"'})
    with fixture.connect() as db:original={k:db.execute('SELECT * FROM task_outbox').fetchone()[k] for k in ('command_id','event_id','body_hash','body')}
    process.terminate();process.wait(timeout=15)
    with Store(database).connect() as db:assert db.execute('SELECT count(*) FROM worker_lease').fetchone()[0]==0
    process=start();pids.append(process.pid)
    assert any(row['account_id']==created['account_id'] for row in call('/api/v1/hunter/accounts')['items'])
    assert call(path)['project']['notes']=='OS persistent research'
    process.kill();process.wait(timeout=5);time.sleep(16)
    process=start();pids.append(process.pid)
    assert any(row['account_id']==created['account_id'] for row in call('/api/v1/hunter/accounts')['items'])
    assert call(path,{'notes':'OS persistent research'},method='PATCH',extra=patch_headers)==patch
    assert call('/internal/v1/commands/'+command['command_id'])['command_id']==command['command_id']
    state=call('/internal/v1/status');assert state['worker_alive'] and state['daily_reserved']=={} and state['external_io_enabled'] is False
    assert call('/health/ready')['source_status']=='未连接真实来源'
    process.terminate();process.wait(timeout=15);process=None
    subprocess.run([sys.executable,'-m','hunterradar','migrate'],cwd=folder,env=env,check=True,capture_output=True)
    dto=FormalService(fixture).discovery(identifier)
    code="""import os,sys,uuid
from pathlib import Path
from hunterradar.store import Store
from hunterradar.formal import FormalService
from hunterradar.protocol import Principal
s=Store(Path(sys.argv[1]));s.audit=lambda *a,**k:os._exit(77)
FormalService(s).write(Principal(user_id='fixture-admin',tenant_id='ikun-main',role='superadmin'),'PATCH',sys.argv[2],{'notes':'must rollback after kill'},str(uuid.uuid4()),sys.argv[3],'kill-fixture')
"""
    killed=subprocess.run([sys.executable,'-c',code,str(database),path,f'"rev-{dto["revision"]}"'],cwd=folder,env=env)
    assert killed.returncode==77
    after=FormalService(fixture).discovery(identifier);assert after['revision']==dto['revision'] and after['project']['notes']==dto['project']['notes']
    with fixture.connect() as db:assert {k:db.execute('SELECT * FROM task_outbox').fetchone()[k] for k in original}==original
    cleaned=fixture.cleanup(now+604800);destination=folder/'restored'/'hunter.db'
    restored=subprocess.run([sys.executable,'-m','hunterradar','restore','--bundle',cleaned['backup'],'--destination',str(destination),'--current',str(database)],cwd=folder,env=env,check=True,capture_output=True,text=True)
    recovery=json.loads(restored.stdout);assert recovery['restored']
    final=Store(destination)
    with final.connect() as db:
        assert db.execute('SELECT count(*) FROM discoveries').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM target_discovery_ledger').fetchone()[0]==1
        assert db.execute('SELECT command_id FROM task_outbox').fetchone()[0]==command['command_id']
    result={'status':'passed','starts':3,'entry':'Node24 execve -> Python','graceful_restart':True,'sigkill_lease_recovery':True,'same_account_id':True,'website_process_required':False,'provider_calls':0,'process_ids':pids,'research_and_confirmation_survive':True,'same_patch_key_replays_after_restart':True,'kill_inside_transaction_exit':77,'transaction_rolled_back':True,'cli_init_migrate_restore':True,'expired_discovery_not_revived':True,'outbox_ids_hash_body_preserved':True}
    evidence=MODULE/'docs/b4';evidence.mkdir(exist_ok=True);(evidence/'process-smoke-night.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:
    if process and process.poll() is None:process.terminate();process.wait(timeout=15)
