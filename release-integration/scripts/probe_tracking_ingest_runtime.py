#!/usr/bin/env python3
"""No valid event POST: verify authorization/422/404 and unchanged Projects rows on the owned runtime."""
import argparse
import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
import httpx
from deploy_c0_lite import ROOT,TARGET
from night_worker_ops import private_json

def snapshot():
 with closing(sqlite3.connect((TARGET/'data/projects/projects.db').as_uri()+'?mode=ro',uri=True)) as db:
  names=[r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
  assert all(re.fullmatch('[A-Za-z0-9_]+',n) for n in names)
  return {n:hashlib.sha256(json.dumps(sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr),ensure_ascii=False,default=str,separators=(',',':')).encode()).hexdigest() for n in names}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--expected-sha',required=True);args=parser.parse_args()
 owner=private_json(TARGET/'owner.json');env=private_json(TARGET/'config/web.environment.json')
 assert owner['candidate_sha']==env['IKUN_RELEASE_SHA']==args.expected_sha
 token=env['PROJECTS_INGEST_TRACKING_TOKEN'];assert len(token)>=32
 before=snapshot();rows=[]
 path='/internal/v1/ingest/tracking';unknown='/internal/v1/receipts/tracking/evt_'+str(uuid.uuid4())
 with httpx.Client(base_url='http://127.0.0.1:4000',trust_env=False,timeout=8) as client:
  for method,target,headers,expected in [('POST',path,{},401),('POST',path,{'authorization':'Bearer '+env['PROJECTS_INGEST_HUNTER_TOKEN']},401),('POST',path,{'authorization':'Bearer '+token,'x-scope':'foreign'},403),('POST',path,{'authorization':'Bearer '+token},422),('GET',unknown,{'authorization':'Bearer '+token,'x-expected-event-sha256':'0'*64},404)]:
   response=client.request(method,target,headers={'content-type':'application/json',**headers},**({'content':b'{}'} if method=='POST' else {}))
   body=response.json();rows.append({'method':method,'path':target,'status':response.status_code,'error_code':body.get('error',{}).get('code'),'request_id_present':bool(body.get('request_id'))})
   assert response.status_code==expected and 'data' not in body and body.get('request_id'),rows[-1]
 assert snapshot()==before,'READONLY_PROBES_MUST_NOT_CHANGE_PROJECTS_ROWS'
 result={'state':'PASS_RECEIVER_NONMUTATING_RUNTIME_PROBES','candidate_sha':args.expected_sha,'probes':rows,'Projects_table_fingerprints_unchanged':before,'valid_event_posts':0,'provider_calls':0,'worker_ACK_or_pending_mutation':False}
 p=ROOT/'release-integration/.runtime/tracking-ingest/runtime-probes.json';p.write_text(json.dumps(result,indent=2)+'\n');p.chmod(0o600)
 print(json.dumps({'state':result['state'],'statuses':[r['status'] for r in rows],'Projects_rows_unchanged':True}))

if __name__=='__main__':main()
