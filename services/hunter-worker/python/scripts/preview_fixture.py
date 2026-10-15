"""Browser QA only: synthetic events in var/browser/hunter.db; NO worker/network clients."""
from pathlib import Path
import sys
import time
import os

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from hunterradar.api import create_app
from hunterradar.config import Settings
from hunterradar.parsers import Follow, Target
from hunterradar.store import Store

settings=Settings(db=Path(os.environ.get('HUNTER_FIXTURE_DB','var/browser/hunter.db')),port=int(os.environ.get('HUNTER_FIXTURE_PORT','18766')))
store=Store(settings.db,initialize=True)  # Explicit isolated fixture provisioning, never serve-time DDL.
now=time.time()
if not store.hunters():
    for i in (1,2):
        row=store.add('fixture_hunter'+str(i),now=now-200)
        store.apply_profile(row,str(100+i),'Synthetic Hunter '+str(i),5000,now-200)
        store.establish_wss_baseline([store.hunter(row['id'])],now-200)
        for j in range(24):
            target=Target('fixture_proj'+str(j),str(900+j),'Fixture Project '+str(j),'合成数据，仅用于隔离验收')
            store.ingest_wss(Follow(row['username'],target,now-100+j,now,'6551_WSS',f'fixture:{i}:{j}'))
app=create_app(settings,store=store,worker=False)
uvicorn.run(app,host='127.0.0.1',port=settings.port,proxy_headers=False,access_log=False)
