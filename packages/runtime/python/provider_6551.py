"""Process-shared 6551 REST accounting, circuit breaker and bounded recovery jobs.

Only operational metadata lives here; no credentials, request bodies or tweet text.
WSS never calls this gate. All network attempts reserve durably before transport.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

TZ=timezone(timedelta(hours=8))
ENDPOINTS=frozenset(('twitter_watch','twitter_user_info','twitter_user_by_id',
    'twitter_user_tweets','twitter_search','twitter_watch_add','twitter_watch_delete'))


class Blocked(Exception):
    def __init__(self,code,retry_after=60):
        self.code,self.retry_after=code,max(1,retry_after)
        super().__init__(code)


def configured():
    path=os.environ.get('IKUN_6551_LEDGER')
    return Ledger(Path(path)) if path else None


def tracking_backfill_enabled():
    """Tweet recovery is opt-in; a zero daily budget also closes every entry point."""
    return (os.environ.get('IKUN_TRACKING_BACKFILL_ENABLED','0')=='1' and
            int(os.environ.get('IKUN_6551_BACKFILL_DAILY_LIMIT','0'))>0)


def quota_response(response):
    if response.status_code==402:return True
    if response.status_code!=200:return False
    try:
        d=response.json()
        msg=str(d.get('error',d.get('message',d.get('msg','')))).lower()
        return d.get('success') is False and any(x in msg for x in ('insufficient quota','quota exhausted','额度不足','余额不足'))
    except (ValueError,AttributeError):return False


def response_error(response):
    if response.status_code!=200:return 'http_error'
    try:
        d=response.json()
        return None if isinstance(d,dict) and d.get('success') is True else 'application_error'
    except ValueError:return 'invalid_json'


def wss_auth_delay(failures):
    """401 is never retried more often than once per minute (ten-minute cap)."""
    return min(600,60*2**min(max(0,failures-1),4))


class Ledger:
    def __init__(self,path,*,clock=time.time):
        self.path=Path(path).absolute();self.clock=clock
        if self.path.is_symlink():raise ValueError('provider_ledger_symlink_forbidden')
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS calls(
              id TEXT PRIMARY KEY,at REAL NOT NULL,day TEXT NOT NULL,program TEXT NOT NULL,
              endpoint TEXT NOT NULL,purpose TEXT NOT NULL,status_code INTEGER,error TEXT,
              finished REAL,probe INTEGER NOT NULL DEFAULT 0,job_key TEXT);
              CREATE INDEX IF NOT EXISTS call_day ON calls(day,purpose);
              CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS recovery_jobs(
              key TEXT PRIMARY KEY,subscription_id TEXT NOT NULL,generation INTEGER NOT NULL,
              handle TEXT NOT NULL,from_at REAL NOT NULL,to_at REAL NOT NULL,
              reason TEXT NOT NULL,state TEXT NOT NULL,created_at REAL NOT NULL,call_id TEXT);''')
            if self.get(db,'recording_since') is None:self.put(db,'recording_since',self.clock())
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
        try:yield db
        finally:
            if db.in_transaction:db.rollback()
            db.close()

    @staticmethod
    def get(db,key,default=None):
        row=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def put(db,key,value):
        db.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))

    def day(self):return datetime.fromtimestamp(self.clock(),TZ).strftime('%Y-%m-%d')

    def limits(self):
        return max(1,int(os.environ.get('IKUN_6551_DAILY_LIMIT','300'))),max(0,int(os.environ.get('IKUN_6551_BACKFILL_DAILY_LIMIT','0')))

    def next_day(self):
        now=datetime.fromtimestamp(self.clock(),TZ)
        return (now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)).timestamp()-self.clock()

    def trip_quota(self,*,initial=False):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');old=self.get(db,'circuit',{})
            n=max(1,old.get('failures',0)+(0 if initial and old else 1))
            self.put(db,'circuit',{'open':True,'failures':n,'next_probe':self.clock()+min(21600,3600*2**min(n-1,4))})
            db.commit()
        self.publish()

    def cached_watch(self):
        with self.db() as db:
            d=self.get(db,'watch_snapshot');requested=self.get(db,'watch_requested_at',0)
        return d['payload'] if d and d['at']>=requested else None

    def request_watch_check(self,*,force=False):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');cached=self.get(db,'watch_snapshot')
            # Coalesce the two workers' startup/reconnect notifications.
            if force or not cached or self.clock()-cached['at']>=30:
                self.put(db,'watch_requested_at',self.clock())
            db.commit()

    def watch_pending(self):
        with self.db() as db:
            requested=self.get(db,'watch_requested_at',0);cached=self.get(db,'watch_snapshot')
        return bool(requested and (not cached or cached['at']<requested))

    def wss_rejected(self,engine):
        with self.db() as db:self.put(db,'wss_paused_'+engine,True)
        self.publish()

    def wss_recovered(self,engine):
        with self.db() as db:
            self.put(db,'wss_paused_'+engine,False)
        # A working stream is not evidence that paid REST quota has recovered.
        self.request_watch_check();self.publish()

    def cache_watch(self,payload):
        data=payload.get('data') if isinstance(payload,dict) else None
        rows=data.get('list',data.get('items')) if isinstance(data,dict) else data
        if not isinstance(rows,list) or (isinstance(data,dict) and data.get('total',len(rows))!=len(rows)):return
        names=[str(x.get('twAccount',x.get('username',''))).lower().lstrip('@') for x in rows if isinstance(x,dict)]
        if len(names)!=len(rows) or len(set(names))!=len(names) or any(not re.fullmatch(r'[a-z0-9_]{1,15}',n) for n in names):return
        allowed={'twAccount','username','id','twGroupId','groupName','remark','isPaused','isSuspended','isBlacked',
                 'newTweetBol','newFlwBol','newUnFlwBol','newTweetReplyBol','newTweetQuoteBol','newRetweetBol',
                 'updateNameBol','updateDescBol','updateAvatarBol','updateBannerBol','newCaBol','tweetToppingBol'}
        safe={'success':True,'data':[{k:v for k,v in row.items() if k in allowed and type(v) in (str,int,bool,type(None))} for row in rows]}
        with self.db() as db:self.put(db,'watch_snapshot',{'at':self.clock(),'payload':safe})

    def begin(self,program,endpoint,*,purpose='read',job_key=None):
        if endpoint not in ENDPOINTS or not re.fullmatch(r'[a-z_]{1,40}',program):raise ValueError('unapproved_provider_route')
        if program=='tracking' and endpoint not in ('twitter_watch','twitter_watch_add','twitter_watch_delete') and not tracking_backfill_enabled():
            raise Blocked('backfill_disabled',86400)
        now=self.clock();day=self.day();limit,backfill_limit=self.limits();probe=False
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');circuit=self.get(db,'circuit',{})
            if circuit.get('open'):
                delay=circuit.get('next_probe',now+3600)-now
                if endpoint!='twitter_watch' or delay>0:raise Blocked('quota_exhausted',max(60,delay))
                probe=True
            used=db.execute('SELECT count(*) FROM calls WHERE day=?',(day,)).fetchone()[0]
            if used>=limit:raise Blocked('daily_budget_exhausted',self.next_day())
            if purpose=='backfill' and db.execute("SELECT count(*) FROM calls WHERE day=? AND purpose='backfill'",(day,)).fetchone()[0]>=backfill_limit:
                raise Blocked('backfill_daily_limit',self.next_day())
            if db.execute('SELECT 1 FROM calls WHERE finished IS NULL AND at>? LIMIT 1',(now-90,)).fetchone():
                raise Blocked('provider_busy',1)
            if job_key:
                job=db.execute('SELECT state FROM recovery_jobs WHERE key=?',(job_key,)).fetchone()
                if not job or job['state']!='pending':raise Blocked('recovery_already_attempted',86400)
            token=str(uuid.uuid4())
            db.execute('INSERT INTO calls(id,at,day,program,endpoint,purpose,probe,job_key) VALUES(?,?,?,?,?,?,?,?)',
                       (token,now,day,program,endpoint,purpose,int(probe),job_key))
            if job_key:db.execute("UPDATE recovery_jobs SET state='attempted',call_id=? WHERE key=?",(token,job_key))
            if probe:
                circuit['next_probe']=now+min(21600,3600*2**min(circuit.get('failures',1),4))
                self.put(db,'circuit',circuit)
            db.commit()
        self.publish();return token

    def finish(self,token,status_code=None,error=None,*,quota=False):
        # Error values are classifications, never exception messages or remote bodies.
        error=error if error and re.fullmatch(r'[A-Za-z0-9_]{1,64}',error) else None
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM calls WHERE id=?',(token,)).fetchone()
            if row is None:return
            db.execute('UPDATE calls SET status_code=?,error=?,finished=? WHERE id=?',
                       (status_code,'quota_exhausted' if quota else error,self.clock(),token))
            if quota:
                old=self.get(db,'circuit',{});n=old.get('failures',0)+1
                self.put(db,'circuit',{'open':True,'failures':n,'next_probe':self.clock()+min(21600,3600*2**min(n-1,4))})
            elif row['probe']:
                if status_code==200 and error is None:self.put(db,'circuit',{'open':False,'failures':0,'next_probe':0})
                else:
                    old=self.get(db,'circuit',{});n=old.get('failures',0)+1
                    self.put(db,'circuit',{'open':True,'failures':n,'next_probe':self.clock()+min(21600,3600*2**min(n-1,4))})
            if row['job_key']:db.execute("UPDATE recovery_jobs SET state=? WHERE key=?",('completed' if status_code==200 and not quota and error is None else 'failed',row['job_key']))
            db.commit()
        logging.getLogger('ikun.6551.rest').warning(json.dumps({'audit':'6551-rest-v1','at':row['at'],
            'program':row['program'],'endpoint':row['endpoint'],'status_code':status_code,
            'error':'quota_exhausted' if quota else error},separators=(',',':')))
        self.publish()

    def summary(self):
        limit,cap=self.limits();day=self.day()
        with self.db() as db:
            rows=[dict(r) for r in db.execute('SELECT program,count(*) calls FROM calls WHERE day=? GROUP BY program',(day,))]
            used=sum(r['calls'] for r in rows)
            backfills=db.execute("SELECT count(*) FROM calls WHERE day=? AND purpose='backfill'",(day,)).fetchone()[0]
            circuit=self.get(db,'circuit',{})
            recording_since=self.get(db,'recording_since')
            realtime_paused=self.get(db,'wss_paused_tracking',False)
        return {'checked_at':self.clock(),'day':day,'timezone':'Asia/Shanghai','used':used,'limit':limit,
                'by_program':rows,'backfill_used':backfills,'backfill_limit':cap,'quota_exhausted':bool(circuit.get('open')),
                'recording_since':recording_since,
                'realtime_paused':realtime_paused,
                'next_probe_at':circuit.get('next_probe',0),'daily_limit_reached':used>=limit or (cap>0 and backfills>=cap)}

    def publish(self):
        path=self.path.parent/'6551-status.json';temp=path.with_name(path.name+'.'+uuid.uuid4().hex)
        try:
            temp.write_text(json.dumps(self.summary(),ensure_ascii=False)+'\n');temp.chmod(0o600);os.replace(temp,path)
        finally:
            if temp.exists():temp.unlink()

    def mark_gap(self,start):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');old=self.get(db,'tracking_gap')
            self.put(db,'tracking_gap',min(start,old) if old else start);db.commit()

    def close_gap(self,end,rows):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');start=self.get(db,'tracking_gap')
            if start and end>start:
                for row in rows:self._enqueue(db,row,start,end,'reconnect',str(round(start,3))+':'+str(round(end,3)))
                db.execute("DELETE FROM meta WHERE key='tracking_gap'")
            db.commit()

    def _enqueue(self,db,row,start,end,reason,suffix):
        start=max(start,row['generation_at'])
        if start>end:return
        key=row['subscription_id']+':'+str(row['generation'])+':'+reason+':'+suffix
        db.execute('INSERT OR IGNORE INTO recovery_jobs(key,subscription_id,generation,handle,from_at,to_at,reason,state,created_at) VALUES(?,?,?,?,?,?,?,\'pending\',?)',
            (key,row['subscription_id'],row['generation'],row['handle'],start,end,reason,self.clock()))

    def initial(self,row):
        with self.db() as db:self._enqueue(db,row,row['generation_at'],self.clock(),'initial','once')

    def jobs(self,subscription_id):
        with self.db() as db:return [dict(r) for r in db.execute("SELECT * FROM recovery_jobs WHERE subscription_id=? AND state='pending' ORDER BY created_at LIMIT 8",(subscription_id,))]

    def discard(self,key):
        with self.db() as db:db.execute("UPDATE recovery_jobs SET state='cancelled' WHERE key=? AND state='pending'",(key,))
