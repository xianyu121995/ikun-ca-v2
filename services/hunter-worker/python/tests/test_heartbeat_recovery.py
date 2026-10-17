import pytest
from hunterradar.config import Settings
from hunterradar.engine import Engine

@pytest.mark.parametrize('error,expected', [('heartbeat:ValueError',None), ('rest:ValueError','rest:ValueError')])
async def test_clear_only_own_error_after_three_successes(store,error,expected):
    engine=Engine(Settings(db=store.path),store)
    store.set_state('worker_error',error)
    ticks=[]
    async def pause(_):
        ticks.append(store.states()['worker_error'])
        if len(ticks)==3:engine.stop.set()
    engine.pause=pause
    await engine.heartbeat_loop()
    assert ticks[:2]==[error,error]
    assert store.states()['worker_error']==expected
    await engine.providers.close()

async def test_failed_renew_does_not_clear_error(store):
    engine=Engine(Settings(db=store.path),store)
    store.set_state('worker_error','heartbeat:ValueError')
    def fail():raise ValueError('unsafe_hunter_permissions')
    store.renew_worker=fail
    with pytest.raises(ValueError):await engine.heartbeat_loop()
    assert store.states()['worker_error']=='heartbeat:ValueError'
    await engine.providers.close()

def test_diagnostic_does_not_log_raw_error(store,caplog):
    engine=Engine(Settings(db=store.path),store)
    try:raise ValueError('secret-value-must-not-appear')
    except ValueError as error:engine.record_loop_error('heartbeat',error)
    detail=store.states()['worker_error_detail']
    assert detail['reason'] is None and detail['frames']
    assert 'secret-value-must-not-appear' not in caplog.text
