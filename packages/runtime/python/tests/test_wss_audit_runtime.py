import json
import pytest
from wss_audit import LOGGER,WssAudit,connection,metadata,note


def frame():
    return {'method':'twitter.event','token':'PRIVATE_TOKEN','params':{'eventType':'NEW_TWEET',
        'twAccount':'@VaultStreet_RH','id':123,'remark':'PRIVATE_NOTE',
        'content':{'id':'2112929214269915170','text':'PRIVATE_BODY','api_key':'PRIVATE_KEY'}}}


def records(caplog):return [json.loads(r.message) for r in caplog.records if r.name=='ikun.wss.receive']


def test_allowlist_preserves_correlation_without_raw_content(caplog):
    for engine in ('hunter','tracking'):
        audit=WssAudit(engine);audit.frame(frame()).drop('not_hunter_follower_event')
    rows=records(caplog)
    assert len(rows)==4
    assert {r['engine'] for r in rows}=={'hunter','tracking'}
    assert len({r['connection'] for r in rows})==2
    assert all(r['tweet_id']=='2112929214269915170' and r['account']=='vaultstreet_rh' for r in rows)
    assert all(set(r)<=set(('audit','at','engine','connection','action','event_type','account','tweet_id','provider_event_id','reason')) for r in rows)
    assert 'PRIVATE' not in caplog.text and 'api_key' not in caplog.text


def test_json_string_content_and_malformed_identifiers_are_safe(caplog):
    value=frame();value['params']['content']=json.dumps(value['params']['content'])
    assert metadata(value)['tweet_id']=='2112929214269915170'
    value['params'].update(eventType='PRIVATE_TOKEN',twAccount='bad\nPRIVATE_ACCOUNT',content='PRIVATE_BROKEN_JSON',id='PRIVATE_ID')
    audit=WssAudit('tracking');audit.frame(value).drop('invalid_content_shape')
    assert metadata(value)=={'event_type':'unknown','account':None,'tweet_id':None,'provider_event_id':None}
    assert 'PRIVATE' not in caplog.text


def test_pong_logging_is_bounded(caplog):
    audit=WssAudit('tracking')
    for _ in range(100):audit.pong()
    assert len(records(caplog))==1


def test_log_failure_cannot_break_processing(monkeypatch):
    def broken(*args,**kwargs):raise OSError('PRIVATE_ERROR')
    monkeypatch.setattr(LOGGER,'info',broken)
    WssAudit('hunter').frame(frame()).drop('invalid_json')
    note(broken,'diagnostic_only')


async def test_connection_failure_keeps_exception_and_redacts_message(caplog):
    class Socket:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
    with pytest.raises(RuntimeError,match='PRIVATE_EXCEPTION'):
        async with connection(Socket(),'tracking'):
            raise RuntimeError('PRIVATE_EXCEPTION token=PRIVATE_TOKEN')
    assert [r['action'] for r in records(caplog)]==['connecting','connected','disconnected']
    assert records(caplog)[-1]['reason']=='connection_or_processing_error'
    assert 'PRIVATE' not in caplog.text
