#!/usr/bin/env python3
"""Production Next/managed IPC with synthetic four-store fixtures; never owned runtime data."""
import copy
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
import httpx
from c0_test_fixture import ROOT,NODE,PYTHON,environment,provision,migrate_projects,cli
from accept_b3_site import port,wait_ready,login,seed_hunter,TRACKING_PYTHON
from readonly_entry_matrix import populated

CHECKS=[]
def check(value,name,**details):
 CHECKS.append({'check':name,'result':'PASS' if value else 'FAIL',**details});assert value,name
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()

def main():
 output=ROOT/'release-integration/.runtime/tracking-ingest'/('next-run-'+str(time.time_ns()));output.mkdir(parents=True,mode=0o700)
 scratch=Path(tempfile.mkdtemp(prefix='ikun-ti-next-',dir='/private/tmp'));data=scratch/'data';assert str(data).startswith('/private/tmp/ikun-ti-next-')
 origin='http://127.0.0.1:'+str(port());accounts=provision(data,origin,scratch/'accounts.private.json');migrate_projects(data);seed_hunter(data)
 cfg=scratch/'tracking.json';cfg.write_text(json.dumps({'db_path':str(data/'tracking/tracking.db'),'remote_enabled':False,'dedicated_account':False,'port':port()}));cfg.chmod(0o600)
 initialized=subprocess.run([str(TRACKING_PYTHON),str(ROOT/'services/tracking-worker/python/entry.py'),'init','--config',str(cfg)],env=environment(data,origin),capture_output=True);check(initialized.returncode==0,'four_store_fixture_tracking_initialized')
 untouched={n:hashlib.sha256((data/n/(n+'.db')).read_bytes()).hexdigest() for n in ('hunter','tracking')}
 token=secrets.token_urlsafe(48);private=scratch/'config/web.environment.json';private.parent.mkdir(mode=0o700);private.write_text(json.dumps({'PROJECTS_INGEST_TRACKING_TOKEN':token}));private.chmod(0o600)
 env=environment(data,origin);env.update(PORT=origin.rsplit(':',1)[1],IKUN_RELEASE_SHA=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),PROJECTS_PYTHON=str(PYTHON),IKUN_TRACKING_INGEST_ENV_FILE=str(private),PROJECTS_INGEST_HUNTER_TOKEN=secrets.token_urlsafe(48))
 assert 'PROJECTS_INGEST_TRACKING_TOKEN' not in env
 log=(output/'website.log').open('ab',buffering=0);web=None;report={'state':'RUNNING','checks':CHECKS,'scratch':str(scratch),'build_id':(ROOT/'apps/website/.next/BUILD_ID').read_text().strip(),'real_provider_calls':0,'real_sound':False,'fixture_database_only':True,'live_runtime_writes':0}
 def start():
  process=subprocess.Popen([str(NODE),'scripts/start-c0-lite.mjs'],cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True);wait_ready(origin,process);return process
 try:
  web=start()
  with httpx.Client(base_url=origin,trust_env=False,timeout=15) as admin,httpx.Client(base_url=origin,trust_env=False,timeout=15) as user:
   admin_me=login(admin,origin,accounts['admin']);user_me=login(user,origin,accounts['user'])
   with httpx.Client(base_url=origin,trust_env=False,timeout=15) as forced:login(forced,origin,accounts['forced'])
   def headers():return {'Origin':origin,'Content-Type':'application/json','X-CSRF-Token':admin_me['csrf_token'],'Idempotency-Key':str(uuid.uuid4())}
   fields={'name':'501隔离受理项目','rating':'A','description':'','website_url':None,'notes':'人工备注不可被观察覆盖','category':None,'progress_stage':'watching','progress_percent':None,'token_date':None,'token_date_status':'unconfirmed'}
   created=admin.post('/api/v1/projects',json=fields,headers=headers());check(created.status_code==201,'actual_Next_Project_create');project=created.json()['data'];pid=project['project_id']
   snapshot=admin.get('/api/v1/projects/'+pid).json()['data']
   template=json.loads((ROOT/'modules/projects/protocols/tracking-observations-v1.json').read_text())['examples']['event']
   def event(**changes):
    item=copy.deepcopy(template);p=item['payload'];item['event_id']='evt_'+str(uuid.uuid4());item['project_id']=p['project_id']=pid;p.update(changes);p['activity_id']='act_'+str(uuid.uuid5(uuid.UUID('c018deb2-7ccf-5092-8112-b5c9f71d40be'),json.dumps(['ikun-main',p['subscription_id'],p['tweet_id']],separators=(',',':'))));item['correlation_id']=p['activity_id'];return item
   def post(item=None,*,raw=None,bearer=token,expected=None,source='tracking'):
    body=(canonical(item) if raw is None else raw);body=body.encode() if isinstance(body,str) else body
    hs={'content-type':'application/json',**({'authorization':'Bearer '+bearer} if bearer else {})}
    if expected is not None:hs['x-expected-event-sha256']=expected
    return admin.post('/internal/v1/ingest/'+source,content=body,headers=hs)
   def receipt(item,expected=None):return admin.get('/internal/v1/receipts/tracking/'+item['event_id'],headers={'authorization':'Bearer '+token,**({'x-expected-event-sha256':expected} if expected else {})})
   item=event(text='TI_NEXT_BODY_MUST_NOT_PERSIST')
   check(post(item,bearer=None).status_code==401 and post(item,bearer=env['PROJECTS_INGEST_HUNTER_TOKEN']).status_code==401,'actual_Next_cookie_and_wrong_direction_401')
   check(post(raw='{}').status_code==422,'actual_Next_authorized_invalid_body_422_not501')
   check(receipt(item,digest(item)).status_code==404,'actual_Next_unknown_receipt404')
   first=post(item,expected=digest(item));check(first.status_code==200,'actual_Next_UDS_first_acceptance200');accepted=first.json()['data']
   check(set(accepted)=={'event_id','project_id','receipt_id','accepted_at','duplicate','command_id'} and not accepted['duplicate'] and accepted['command_id'] is None,'unchanged_six_field_receipt')
   check(post(item,expected=digest(item)).json()['data']=={**accepted,'duplicate':True} and receipt(item,digest(item)).json()['data']=={**accepted,'duplicate':True},'actual_Next_idempotent_POST_and_GET')
   changed=copy.deepcopy(item);changed['payload']['text']+='different'
   check(post(changed).status_code==409 and receipt(item,'0'*64).status_code==409,'actual_Next_hash_conflicts409')
   updated=event(tweet_kind='unknown',source='rest',replay=True,is_live_new=False);updated['event_type']='tracking.feed.activity.updated.v1'
   check(post(updated,expected=digest(updated)).status_code==200,'actual_Next_updated_visibility_correction')
   for name,char in [('emoji','😀'),('control',chr(1))]:
    maximum=event(text=char*20000,project_name=char*120,generation=9223372036854775807);maximum['received_at']=maximum['payload']['received_at']='2026-10-16T00:00:01.123456789Z'
    raw=canonical(maximum);check(65536<len(raw.encode())<131072 and post(maximum,expected=digest(maximum)).status_code==200 and receipt(maximum,digest(maximum)).status_code==200,'actual_Next_max_'+name+'_int64_and_raw_time_hash')
   padded=canonical(item);padded+=' '*(131072-len(padded.encode()))
   check(post(raw=padded).status_code==200 and post(raw=padded+' ').status_code==413,'actual_Next_Tracking_exact128KiB_bound')
   check(post(raw=padded,source='hunter',bearer=env['PROJECTS_INGEST_HUNTER_TOKEN']).status_code==422,'actual_Next_Hunter_64KiB_preserved')
   bad=event();bad['payload']['generation']=1.0
   check(post(bad).status_code==422,'actual_Next_fractional_generation_not_coerced')
   bad=event();bad['schema_version']=1.0
   check(post(bad).status_code==422,'actual_Next_fractional_schema_not_coerced')
   surrogate=event(text=chr(0xd800))
   check(post(raw=b'{"x":"\xed\xa0\x80"}').status_code==422 and post(raw=json.dumps(surrogate,ensure_ascii=True)).status_code==422,'actual_Next_invalid_UTF8_and_surrogate')
   lost=event();forwarded=[]
   class DropAck(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
     body=self.rfile.read(int(self.headers['content-length']))
     with httpx.Client(base_url=origin,trust_env=False,timeout=15) as client:r=client.post('/internal/v1/ingest/tracking',content=body,headers={'content-type':'application/json','authorization':'Bearer '+token,'x-expected-event-sha256':digest(lost)})
     forwarded.append((r.status_code,r.json().get('data')));self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();self.close_connection=True
   proxy=ThreadingHTTPServer(('127.0.0.1',0),DropAck);thread=threading.Thread(target=proxy.serve_forever,daemon=True);thread.start()
   dropped=False
   try:
    try:httpx.post('http://127.0.0.1:'+str(proxy.server_port),content=canonical(lost).encode(),trust_env=False,timeout=15)
    except httpx.HTTPError:dropped=True
   finally:proxy.shutdown();proxy.server_close();thread.join(3)
   check(dropped and len(forwarded)==1 and forwarded[0][0]==200 and receipt(lost,digest(lost)).json()['data']=={**forwarded[0][1],'duplicate':True},'actual_Next_lost_ACK_single_POST_then_original_hash_GET')
   fault=event(subscription_id='sub_'+str(uuid.uuid4()))
   with sqlite3.connect(data/'projects/projects.db') as db:db.execute("CREATE TRIGGER ti_fixture_failure BEFORE INSERT ON event_inbox WHEN NEW.event_id='"+fault['event_id']+"' BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
   check(post(fault,expected=digest(fault)).status_code==503 and receipt(fault,digest(fault)).status_code==404,'actual_Next_storage_failure_no_manufactured_receipt')
   with sqlite3.connect(data/'projects/projects.db') as db:
    check(db.execute('select count(*) from project_sources where external_id=?',('observations-v1:subscription:'+fault['payload']['subscription_id'],)).fetchone()[0]==0,'actual_Next_transaction_rolls_back_alias');db.execute('DROP TRIGGER ti_fixture_failure')
   expired=event();scrub={k:v for k,v in expired.items() if k not in ('occurred_at','payload')};scrub['expired']=True
   check(post(scrub).status_code==422 and receipt(expired,digest(expired)).status_code==404,'actual_Next_expired_scrub422_missing_receipt_unknown404')
   check(admin.get('/api/v1/projects/'+pid).json()['data']==snapshot,'observations_preserve_manual_fields_membership_rating_revision')
   web.send_signal(signal.SIGTERM);web.wait(timeout=15);web=start()
   check(receipt(item,digest(item)).json()['data']=={**accepted,'duplicate':True},'actual_Next_restart_preserves_original_receipt')
   for method in ('POST','PATCH','DELETE'):
    response=user.request(method,'/api/v1/projects'+('/'+pid if method!='POST' else ''),json={},headers={'Origin':origin,'X-CSRF-Token':user_me['csrf_token'],'Idempotency-Key':str(uuid.uuid4()),'If-Match':'"rev-1"'})
    check(response.status_code==403,'actual_Next_user_'+method+'_403')
   # Populate presentation categories through the actual server, only in this fixture.
   for name,rating,complete in [('待查看其他项目',None,False),('已完成隔离项目','B',True)]:
    body={'fields':{**fields,'name':name,'rating':rating,'progress_stage':'completed' if complete else 'watching'},'milestone':{'date':None,'hour':None,'title':'','status':'unconfirmed'},'complete':complete}
    created=admin.post('/api/v1/projects?view=home-v1',json=body,headers=headers());check(created.status_code==201,'actual_Next_home_category_create_'+str(complete))
    if not complete:
     row=created.json()['data']['project'];removed=admin.delete('/api/v1/projects/'+row['project_id'],headers={**headers(),'If-Match':'"rev-'+str(row['revision'])+'"'})
     check(removed.status_code==200,'fixture_other_removed_membership_reaches_join_control',status=removed.status_code)
   pages=[]
   for index in range(18):pages.append(admin.post('/api/v1/projects',json={**fields,'name':'隔离分页项目'+str(index)},headers=headers()).status_code)
   check(all(status==201 for status in pages),'fixture_tracked_projects_enable_actual_second_page')
   from playwright.sync_api import sync_playwright
   with sync_playwright() as runtime:
    browser=runtime.chromium.launch(channel='chrome',headless=True)
    try:
     for role in ('admin','user'):
      context=browser.new_context();page=context.new_page();page.goto(origin+'/login');page.locator('input[name=username]').fill(accounts[role]['username']);page.locator('input[name=password]').fill(accounts[role]['password']);page.get_by_role('button',name='登录',exact=True).click();page.wait_for_url(origin+'/',timeout=15000)
      for width in (1440,390):
       page.set_viewport_size({'width':width,'height':1000});page.goto(origin+'/');page.locator('.hpv2-projects tbody tr').first.wait_for();populated(page,role,width,output,check)
      context.close()
    finally:browser.close()
   cli(data,origin,'disable',accounts['user']['username']);check(user.get('/api/v1/projects').status_code==401,'fixture_user_disabled401')
  for name,expected in untouched.items():check(hashlib.sha256((data/name/(name+'.db')).read_bytes()).hexdigest()==expected,'receiver_never_changes_'+name+'_fixture_database')
  with sqlite3.connect(data/'projects/projects.db') as db:
   check(db.execute('pragma integrity_check').fetchone()==('ok',) and not db.execute('pragma foreign_key_check').fetchall(),'receiver_fixture_integrity_FK')
   check(db.execute('select count(*) from tracking_outbox').fetchone()[0]==0,'observations_do_not_create_commands')
  check(all(b'TI_NEXT_BODY_MUST_NOT_PERSIST' not in p.read_bytes() for p in (data/'projects').glob('projects.db*')),'actual_Next_no_tweet_body_in_Projects_DB_or_WAL')
  report['state']='PASS_ACTUAL_NEXT_RECEIVER_AND_READONLY_BROWSER'
 except Exception as error:report.update(state='FAIL',error_type=type(error).__name__,error=str(error)[:240] if isinstance(error,(AssertionError,RuntimeError)) else 'inspect private fixture log');raise
 finally:
  if web and web.poll() is None:
   web.send_signal(signal.SIGTERM)
   try:web.wait(timeout=15)
   except subprocess.TimeoutExpired:os.killpg(web.pid,signal.SIGKILL);web.wait(timeout=5)
  log.close();report['screenshots']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*.png')};path=output/'acceptance.json';path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');path.chmod(0o600);print(json.dumps({'state':report['state'],'checks':len(CHECKS),'receipt':str(path)}))

if __name__=='__main__':main()
