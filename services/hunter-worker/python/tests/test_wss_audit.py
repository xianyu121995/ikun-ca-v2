import json
from conftest import ready
from hunterradar.config import Settings
from hunterradar.engine import Engine


async def test_tweet_frames_are_logged_before_existing_hunter_filter(store,caplog):
    ready(store)
    engine=Engine(Settings(db=store.path,token_6551='PRIVATE_TOKEN'),store)
    accounts=['starcatokx','inkdaddynft','lildudes_','temrushnfts','vaultstreet_rh']
    class Socket:
        def __init__(self):
            self.messages=[json.dumps({'id':1,'result':{'success':True}})]+[
                json.dumps({'method':'twitter.event','params':{'eventType':'NEW_TWEET','twAccount':name,
                    'content':{'id':str(89100+i),'text':'PRIVATE_BODY'}}}) for i,name in enumerate(accounts)]
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        async def send(self,value):pass
        async def recv(self):
            if self.messages:return self.messages.pop(0)
            engine.stop.set();return 'pong'
    engine.connector=lambda *args,**kwargs:Socket()
    try:await engine.consume()
    finally:await engine.providers.close()
    rows=[json.loads(r.message) for r in caplog.records if r.name=='ikun.wss.receive']
    received=[r for r in rows if r['action']=='received']
    assert [r['account'] for r in received]==accounts
    assert len({r['connection'] for r in rows})==1
    assert len([r for r in rows if r.get('reason')=='not_hunter_follower_event'])==5
    with store.connect() as db:assert db.execute('SELECT count(*) FROM follow_events').fetchone()[0]==0
    assert 'PRIVATE_TOKEN' not in caplog.text and 'PRIVATE_BODY' not in caplog.text
