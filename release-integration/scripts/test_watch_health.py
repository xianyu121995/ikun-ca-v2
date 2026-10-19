import json,sqlite3,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parent))
import v2_maintenance as m

@pytest.mark.parametrize('error,since,alert', [('TimeoutError',9101,False),('TimeoutError',9100,False),('TimeoutError',9099,True),(None,None,False)])
def test_watch_health_waits_over_fifteen_minutes(tmp_path,monkeypatch,error,since,alert):
    root=tmp_path; (root/'config').mkdir();(root/'config/web.environment.json').write_text(json.dumps({'TRACKING_API_TOKEN':'fixture'}))
    (root/'data/hunter').mkdir(parents=True)
    with sqlite3.connect(root/'data/hunter/hunter.db') as d:
        d.execute('CREATE TABLE state(key TEXT,value TEXT)')
        d.execute('CREATE TABLE hunters(enabled INTEGER,deleted_at REAL,poll_error TEXT,profile_error TEXT)')
        d.executemany('INSERT INTO state VALUES(?,?)',[(k,json.dumps(v)) for k,v in {'worker_heartbeat':10000,'watch_error':error,'watch_error_since':since}.items()])
    monkeypatch.setattr(m.time,'time',lambda:10000)
    monkeypatch.setattr(m,'get',lambda url,headers=None:{'data':{'items':[]}})
    monkeypatch.setattr(m,'rotate',lambda *a:None)
    errors=m.health(root)
    assert bool(errors)==alert
    if alert:assert '15 分钟' in errors[0]


def test_short_blips_need_three_minutes(tmp_path,monkeypatch):
    root=tmp_path; (root/'config').mkdir();(root/'config/web.environment.json').write_text(json.dumps({'TRACKING_API_TOKEN':'fixture'}))
    (root/'data/hunter').mkdir(parents=True)
    with sqlite3.connect(root/'data/hunter/hunter.db') as d:
        d.execute('CREATE TABLE state(key TEXT,value TEXT)')
        d.execute('CREATE TABLE hunters(enabled INTEGER,deleted_at REAL,poll_error TEXT,profile_error TEXT)')
        d.execute('INSERT INTO state VALUES(?,?)',('worker_heartbeat',json.dumps(10_010_000)))
    clock={'t':10_000_000}
    monkeypatch.setattr(m.time,'time',lambda:clock['t'])
    rows={'items':[{'desired_state':'running','connection':'disconnected'}]}
    monkeypatch.setattr(m,'get',lambda url,headers=None:{'data':rows})
    monkeypatch.setattr(m,'rotate',lambda *a:None)
    assert m.health(root)==[]                      # first sighting: hidden
    clock['t']+=120; assert m.health(root)==[]     # 2 min: still hidden
    clock['t']+=61; assert m.health(root)==['追踪监听中断']   # >3 min: shown
    rows['items'][0]['connection']='connected'
    clock['t']+=60; assert m.health(root)==[]      # recovered: gone at once
    rows['items'][0]['connection']='disconnected'
    clock['t']+=60; assert m.health(root)==[]      # new blip starts a fresh 3-min window
