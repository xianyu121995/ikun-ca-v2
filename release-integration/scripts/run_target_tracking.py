import os,sys,json,asyncio,time,logging
from pathlib import Path
from dataclasses import replace
from urllib.parse import urlencode
os.umask(0o077)
ROOT=Path('/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/target-test')
CODE=ROOT/'code/services/tracking-worker/python'
sys.path.insert(0,str(CODE))
from tracking.config import Config
from tracking.store import Store
from tracking.worker import Worker
from tracking.remote import Remote
from tracking.events import parse_event
from tracking.cli import serve
from tracking.api import create_app
from websockets.asyncio.client import connect
for name in ('httpx','httpcore','websockets'):logging.getLogger(name).setLevel(logging.CRITICAL)
TARGET='0x2a_ikun';PROJECT='prj_974f048b-db6d-4eab-9546-e8b867cd53a3';SUB='sub_8d94faa7-533e-4475-a32c-0a0c4112d7c4'
V2=Path('/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite')
native=json.loads((V2/'config/tracking.environment.307d6e2cfb6102d21ffb5cfd7146f64ed195681f.json').read_text())
os.environ.update({k:v for k,v in native.items()if k in('DATA_ROOT','TRACKING_API_TOKEN')});os.environ.pop('IKUN_TRACKING_EXTERNAL_IO_DISABLED',None)
os.environ['IKUN_TRACKING_6551_TOKEN']=json.loads((ROOT/'config/provider.environment.private.json').read_text())['IKUN_TRACKING_6551_TOKEN']
cfg=replace(Config.load(str(ROOT/'config/tracking.json')),remote_enabled=True,adopt_only=True,heartbeat_seconds=3)
store=Store(cfg.db_path);row=store.get(PROJECT);assert row['handle']==TARGET and row['subscription_id']==SUB and row['x_user_id']=='123997283'
started=time.time();watch=json.loads((ROOT/'config/test-watch.json').read_text())
def proof(row):
 if row['project_id']!=PROJECT or row['subscription_id']!=SUB or row['handle']!=TARGET:return None
 return {'watch_id':str(watch['id']),'x_handle':TARGET,'x_user_id':row['x_user_id'],'groups':{'twGroupId':watch['twGroupId']},'flags':{k:v for k,v in watch.items()if k.endswith('Bol')},'adopted_at':started}
class LoggedSocket:
 def __init__(self,ws):self.ws=ws;self.iterator=ws.__aiter__()
 def __aiter__(self):return self
 async def __anext__(self):
  raw=await self.iterator.__anext__()
  try:
   frame=json.loads(raw);params=frame.get('params')if isinstance(frame,dict)else None
   if isinstance(params,dict)and str(params.get('twAccount','')).lower().removeprefix('@')==TARGET:
    RAW_LOG.info(json.dumps({'received_at':time.time(),'frame':raw.decode()if isinstance(raw,bytes)else raw},ensure_ascii=False))
  except(ValueError,TypeError):pass
  return raw
 async def send(self,value):return await self.ws.send(value)
import logging.handlers
raw_path=ROOT/'logs/target-raw-wss.jsonl'
fd=os.open(raw_path,os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600);os.close(fd);raw_path.chmod(0o600)
RAW_LOG=logging.getLogger('target.raw.private');RAW_LOG.setLevel(logging.INFO);RAW_LOG.propagate=False
RAW_LOG.addHandler(logging.handlers.RotatingFileHandler(raw_path,maxBytes=8*1024*1024,backupCount=3,encoding='utf-8'))
class TargetWorker(Worker):
 def ingest(self,message):
  params=message.get('params')if isinstance(message,dict)else None
  if not isinstance(params,dict)or str(params.get('twAccount','')).lower().removeprefix('@')!=TARGET:return False
  parsed=parse_event(message)
  if not parsed or parsed[0]!=TARGET:return False
  row=self.store.get(PROJECT);self.store.observe(row,claim='owned',remote_state='active',observed_at=time.time(),status='running',error=None)
  accepted=super().ingest(message)
  if accepted:print(json.dumps({'state':'TARGET_TWEET_STORED','tweet_id':parsed[1].get('tweet_id'),'source':'wss'}),flush=True)
  return accepted
 async def run(self):
  self.acquire()
  # Explicit user-confirmed correction; never claim that an absent old raw frame exists.
  row=self.store.get(PROJECT)
  with self.store.connect()as db:
   saved={r['tweet_id']:dict(r)for r in db.execute('SELECT * FROM tweets WHERE subscription_id=?',(SUB,))}
  for identifier,item in saved.items():
   kind='original'if identifier=='2111117786974228500'else item['tweet_kind']
   tweet={'tweet_id':identifier,'created_at':item['created_at'],'text':item['text'],'tweet_kind':kind,'author_verified':True,'author_handle':TARGET,'author_id':row['x_user_id'],'type_evidence_version':'human-confirmed-original-v1'if kind!=item['tweet_kind']else item['type_evidence_version']}
   # Only this exact self-quote points to a real WSS original already in this DB.
   if identifier=='2111117963021697391'and '2111117786974228500'in saved:
    original=saved['2111117786974228500'];tweet['quoted_tweet']={'tweet_id':original['tweet_id'],'text':original['text'],'author_handle':original['handle'],'author_name':original['handle'],'url':'https://x.com/'+original['handle']+'/status/'+original['tweet_id']}
   if kind!=item['tweet_kind']or tweet.get('quoted_tweet'):self.store.insert_tweet(row,tweet,'wss')
  self.store.runtime(connection='connecting',pong_at=None,error=None)
  async def connected():
   while not self.stop.is_set():
    with self.store.connect()as db:r=db.execute('select connection,pong_at from runtime where id=1').fetchone()
    if r['connection']=='connected'and r['pong_at']and r['pong_at']>=started:
     print(json.dumps({'state':'TARGET_WSS_CONNECTED_ACK_AND_PONG','target':TARGET,'port':cfg.port,'started_at':started}),flush=True);return
    await asyncio.sleep(.1)
  tasks=[]
  try:
   async with connect('wss://ai.6551.io/open/twitter_wss?'+urlencode({'token':cfg.secret('token')}),open_timeout=15,close_timeout=2,ping_interval=None,max_size=1024*1024,max_queue=64)as ws:
    tasks=[asyncio.create_task(self.session(LoggedSocket(ws))),asyncio.create_task(self.stop.wait()),asyncio.create_task(connected())]
    done,_=await asyncio.wait(tasks[:2],return_when=asyncio.FIRST_COMPLETED)
    for task in done:task.result()
  except Exception as error:
   print(json.dumps({'state':'TARGET_WSS_STOPPED','code':getattr(error,'code',type(error).__name__)}),flush=True)
  finally:
   for task in tasks:task.cancel()
   await asyncio.gather(*tasks,return_exceptions=True);await self.remote.close();self.release()
async def main():
 worker=TargetWorker(cfg,store,Remote(cfg),proof_reader=proof);await serve(cfg,worker=worker,app=create_app(cfg,store,read_only=True),log_level='critical')
asyncio.run(main())
