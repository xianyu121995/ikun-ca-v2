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

@pytest.mark.parametrize('error,expected', [('profiles:ValueError',None), ('rest:ValueError','rest:ValueError')])
async def test_profiles_clear_only_after_three_successful_passes(store,error,expected):
    engine=Engine(Settings(db=store.path),store)
    store.set_state('worker_error',error)
    ticks=[]
    async def pause(_):
        ticks.append(store.states()['worker_error'])
        if len(ticks)==3:engine.stop.set()
    engine.pause=pause
    await engine.profile_loop()
    assert ticks[:2]==[error,error]
    assert store.states()['worker_error']==expected
    assert store.states()['profiles_checked_at']>0
    await engine.providers.close()

def test_detached_sidecar_does_not_fail_private_location(store,monkeypatch):
    from hunterradar.migration import location
    from pathlib import Path
    from types import SimpleNamespace
    import stat
    original=Path.lstat
    sidecar=Path(str(store.path)+'-wal')
    def race(path,*args,**kwargs):
        if path==sidecar:return SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_nlink=0)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',race)
    assert location(store.path,require_exists=True)==store.path

@pytest.mark.parametrize('sidecar,links',[(True,2),(False,0)])
def test_hardlinks_and_detached_main_remain_forbidden(store,monkeypatch,sidecar,links):
    from hunterradar.migration import location
    from pathlib import Path
    from types import SimpleNamespace
    import stat
    original=Path.lstat
    target=Path(str(store.path)+'-wal') if sidecar else store.path
    def race(path,*args,**kwargs):
        if path==target:return SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_nlink=links)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',race)
    with pytest.raises(ValueError,match='database_must_be_private_regular_file'):
        location(store.path,require_exists=True)
