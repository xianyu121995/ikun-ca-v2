"""Three real OS starts, graceful restart and crash/lease recovery; no provider IO."""
import json,os,secrets,socket,sqlite3,subprocess,time,uuid
from pathlib import Path
from urllib.request import Request,urlopen

module=Path(__file__).resolve().parents[1]
root=module.parents[2]
node=root.parent.parent/'ikun-ca-v2/.tools/node/bin/node'
assert node.is_file()
data=module/'var'/('process-smoke-'+str(uuid.uuid4()))
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
admin=secrets.token_urlsafe(32)
env=dict(os.environ,DATA_ROOT=str(data),HUNTER_ENGINE='python',HUNTER_EXTERNAL_IO_ENABLED='0',
         HUNTER_API_TOKEN=admin,HUNTER_VIEW_TOKEN=secrets.token_urlsafe(32),HUNTER_PORT=str(port),
         OPENNEWS_TOKEN='',TWITTERAPI_IO_API_KEY='',HUNTER_PROJECT_TASK_URL='',HUNTER_SECRETS_FILE='')
base=f'http://127.0.0.1:{port}'
def call(path,body=None):
    req=Request(base+path,data=json.dumps(body).encode() if body else None,headers={'Authorization':'Bearer '+admin,'Content-Type':'application/json'})
    with urlopen(req,timeout=2) as response:return json.load(response)
def start():
    process=subprocess.Popen([str(node),'services/hunter-worker/dist/main.js'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(120):
        if process.poll() is not None:raise RuntimeError('child_start_failed')
        try:
            value=call('/internal/v1/status')
            if value['data']['worker_alive']:return process,value
        except Exception:pass
        time.sleep(.1)
    process.kill();process.wait();raise RuntimeError('startup_deadline')
process=None
try:
    process,status=start();pids=[process.pid]
    assert status['data']['external_io_enabled'] is False
    created=call('/api/hunterradar/v1/hunters',{'username':'smoke_hunter','note':'isolated process smoke'})
    process.terminate();assert process.wait(timeout=15) in (0,-15)
    with sqlite3.connect(f'{(data/"hunter/hunter.db").as_uri()}?mode=ro',uri=True) as db:
        assert db.execute('SELECT count(*) FROM worker_lease').fetchone()[0]==0
    process,status=start();pids.append(process.pid)
    assert call('/api/hunterradar/v1/hunters')['items'][0]['id']==created['id']
    process.kill();process.wait(timeout=5)
    time.sleep(16)  # Real lease expiry after SIGKILL, no manual DB mutation.
    process,status=start();pids.append(process.pid)
    assert status['data']['daily_reserved']=={}
    assert call('/api/hunterradar/v1/hunters')['items'][0]['id']==created['id']
    result={'status':'passed','starts':3,'graceful_restart':True,'sigkill_recovery_after_lease_expiry':True,
            'external_io_enabled':False,'provider_requests':0,'same_hunter_id_after_restart':True,'process_ids':pids}
    (module/'docs/process-smoke.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
finally:
    if process and process.poll() is None:process.terminate();process.wait(timeout=15)
