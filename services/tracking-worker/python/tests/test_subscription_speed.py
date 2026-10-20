import time
from contextlib import contextmanager
from tracking.views import page,subscription
from test_api_store import envelope
from tracking.commands import accept
from tracking.protocol import Command,DomainError
import pytest

def test_complete_subscription_projection_is_batched_and_read_only(store):
    for n in range(125):
        command=envelope(project_id=f'prj_550e8400-e29b-41d4-a716-{n:012d}')
        command['payload']['x_handle']=f'fixture{n}'
        accept(store,Command.model_validate(command),'fixture')
    original=store.connect;queries=[]
    @contextmanager
    def traced():
        with original() as db:
            db.set_trace_callback(queries.append)
            yield db
    store.connect=traced
    before=time.perf_counter();result=page(store,'subscriptions',{'limit':'1000','include_removed':'true'});elapsed=time.perf_counter()-before
    assert len(result['items'])==125 and result['next_cursor'] is None
    assert elapsed<.2
    assert len([q for q in queries if q.lstrip().upper().startswith('SELECT')])<15
    assert not any(q.lstrip().upper().startswith(('UPDATE','INSERT','DELETE')) for q in queries)
    row=store.get(result['items'][0]['project_id']);assert subscription(store,row)==result['items'][0]

@pytest.mark.parametrize('value',['0','1001','invalid'])
def test_complete_list_is_still_bounded(store,value):
    with pytest.raises(DomainError):page(store,'subscriptions',{'limit':value})
def test_activity_limit_unchanged(store):
    with pytest.raises(DomainError):page(store,'latest',{'limit':'101'})
