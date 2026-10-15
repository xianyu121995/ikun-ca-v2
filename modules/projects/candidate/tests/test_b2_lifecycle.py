import json
import os
import signal
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from projects_service.migration import FormalDatabase
from projects_service.service import Service
from test_b2_domain import ADMIN, call, create, uid
from test_b2_browser import INTEGRATION, NODE, ROOT, build_sha

def alive(pid):
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False

@pytest.mark.parametrize('failure',['child_kill','parent_kill','graceful'])
def test_real_b0_ipc_lifecycle_and_restart(tmp_path,failure):
    data=tmp_path/'data';db=FormalDatabase(data/'projects/projects.db');db.migrate();p=create(Service(db))
    env={**os.environ,'DATA_ROOT':str(data),'PROJECTS_PYTHON':str(ROOT/'modules/projects/candidate/.venv/bin/python'),'B2_BUILD_SHA':build_sha()}
    def start(index):
        identity=tmp_path/f'ipc-{index}.json';log=(tmp_path/f'ipc-{index}.log').open('w')
        proc=subprocess.Popen([str(NODE),str(INTEGRATION/'tests/ipc-harness.mjs'),str(identity)],env=env,stdout=log,stderr=log)
        for _ in range(150):
            if identity.exists():return proc,json.loads(identity.read_text()),log
            if proc.poll() is not None:raise AssertionError((tmp_path/f'ipc-{index}.log').read_text())
            time.sleep(.1)
        proc.kill();proc.wait();raise AssertionError('IPC readiness timeout')
    proc,identity,log=start(1);path=Path(identity['socketPath'])
    try:
        assert path.stat().st_mode & 0o777==0o600 and path.parent.stat().st_mode & 0o777==0o700
        with httpx.Client(transport=httpx.HTTPTransport(uds=str(path)),base_url='http://ipc',timeout=2) as client:
            assert client.get('/health/ready',headers={'authorization':'Bearer '+identity['token']}).status_code==200
            assert client.get('/health/ready',headers={'authorization':'Bearer wrong'}).status_code==401
            assert client.post('/v1/rpc',headers={'authorization':'Bearer '+identity['token'],'x-ikun-build-sha':'f'*40},json={}).status_code==403
        if failure=='child_kill':os.kill(identity['child'],signal.SIGKILL)
        if failure=='parent_kill':proc.kill()
        else:proc.terminate()
        proc.wait(timeout=15)
        for _ in range(150):
            if not alive(identity['child']) and not path.exists():break
            time.sleep(.1)
        assert not alive(identity['child']) and not path.exists()
        # B0 parent SIGKILL leaves an empty private directory; no live socket/secret remains.
        if path.parent.exists():path.parent.rmdir()
    finally:
        if proc.poll() is None:proc.terminate();proc.wait(timeout=15)
        log.close()
    restarted,second,log=start(2)
    try:
        assert second['socketPath']!=identity['socketPath'] and second['token']!=identity['token']
        with httpx.Client(transport=httpx.HTTPTransport(uds=second['socketPath']),base_url='http://ipc') as client:
            response=client.post('/v1/rpc',headers={'authorization':'Bearer '+second['token'],'x-ikun-build-sha':second['buildSha']},json={'operation':'get','principal':ADMIN,'target':p['project_id'],'request_id':uid()})
            assert response.status_code==200 and response.json()['data']['project_id']==p['project_id']
    finally:restarted.terminate();restarted.wait(timeout=15);log.close()
