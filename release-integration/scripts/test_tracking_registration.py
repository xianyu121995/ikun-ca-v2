import uuid
import pytest
from projects_service.migration import FormalDatabase
from projects_service.service import Service
from projects_service.transport import Rpc
from projects_service.db import DomainError

ADMIN={'user_id':'test_admin','tenant_id':'ikun-main','role':'superadmin'}
def test_hidden_registration_idempotency_and_readonly(tmp_path):
    db=FormalDatabase(tmp_path/'projects/projects.db');db.migrate();service=Service(db)
    body={'name':'Fixture project','x_handle':'FixtureHandle','notes':'Fixture notes','rating':'S'}
    def register(key,principal=ADMIN):return service.execute(Rpc(operation='tracking_register',principal=principal,request_id=str(uuid.uuid4()),idempotency_key=key,body=body))
    key=str(uuid.uuid4());first=register(key);again=register(key);alias=register(str(uuid.uuid4()))
    assert first[1]['project_id']==again[1]['project_id']==alias[1]['project_id']
    assert first[1]['home_membership']=='hidden' and first[1]['rating']=='S'
    with pytest.raises(DomainError) as exc:register(str(uuid.uuid4()),{**ADMIN,'role':'user'})
    assert exc.value.status==403

def test_project_removal_commits_durable_tracking_cleanup(tmp_path):
    db=FormalDatabase(tmp_path/'projects/projects.db');db.migrate();service=Service(db)
    def call(operation,**kwargs):return service.execute(Rpc(operation=operation,principal=ADMIN,request_id=str(uuid.uuid4()),idempotency_key=str(uuid.uuid4()),**kwargs))
    project=call('tracking_register',body={'name':'Fixture','x_handle':'Fixture2','rating':'A'})[1]
    call('membership',target=project['project_id'],if_match='"rev-1"',body={'action':'remove'})
    with db.connect() as con:
        row=con.execute('SELECT command_json,state FROM tracking_outbox').fetchone()
        import json
        command=json.loads(row['command_json'])
        assert row['state']=='pending' and command['operation']=='tracking.remove' and command['project_id']==project['project_id']
