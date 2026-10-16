#!/usr/bin/env python3
"""Exactly one test-profile read and one full Watch read; default is local dry-run."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from takeover_backup import require,SafeFailure,private_dir,atomic,artifact,sha,read_json,utc
import tracking_only_maintenance as ops

TARGET='0x2a_ikun'
MAX_SECONDS=35
READS=('twitter_user_info','twitter_watch')


def identity(envelope):
 require(isinstance(envelope,dict) and envelope.get('success') is True and isinstance(envelope.get('data'),dict),'PROFILE_ENVELOPE_REJECTED')
 data=envelope['data'];identifier=data.get('userId');name=str(data.get('screenName','')).lower().removeprefix('@');followers=data.get('followersCount')
 require(type(identifier) is str and re.fullmatch('[1-9][0-9]{0,39}',identifier) and name==TARGET,'PROFILE_STABLE_ID_UNPROVEN')
 require(type(followers) is int and 0<=followers<=9223372036854775807,'PROFILE_FOLLOWERS_UNPROVEN')
 return {'x_handle':TARGET,'x_user_id':identifier,'followers':followers,'hunter_mode':'WSS' if followers>=5000 else 'REST'}


def watch_result(envelope,normalized,capacity,ownership,profile):
 require(isinstance(envelope,dict) and envelope.get('success') is True and not envelope.keys()-{'success','data','total','usage','code','msg','message'},'WATCH_ENVELOPE_REJECTED');data=envelope.get('data')
 if isinstance(data,dict):
  require(not data.keys()-{'list','items','total','usage'},'WATCH_PAGINATION_OR_UNKNOWN_FIELDS')
  rows=data.get('list',data.get('items'));require(isinstance(rows,list) and ('total' in data or 'total' in envelope),'WATCH_COMPLETENESS_UNPROVEN')
  if 'total' in data:require(type(data['total']) is int and data['total']==len(rows),'WATCH_COMPLETENESS_UNPROVEN')
  require('list' not in data or 'items' not in data or data['list']==data['items'],'WATCH_LIST_ALIAS_CONFLICT')
 else:rows=data
 require(isinstance(rows,list) and len(rows)==len(normalized),'WATCH_COMPLETENESS_UNPROVEN')
 if 'total' in envelope:require(type(envelope['total']) is int and envelope['total']==len(rows),'WATCH_TOP_TOTAL_CONFLICT')
 seen=set()
 for row in rows:
  identifier=row.get('id');require(type(identifier) in (str,int) and not (type(identifier) is int and identifier<0) and re.fullmatch('[A-Za-z0-9_.:-]{1,128}',str(identifier)) and str(identifier) not in seen,'WATCH_ID_UNPROVEN_OR_DUPLICATE');seen.add(str(identifier))
  require(type(row.get('newTweetBol')) is bool and all(type(value) is bool for key,value in row.items() if key.endswith('Bol')),'WATCH_FLAGS_UNPROVEN')
 require(capacity is not None and capacity['new_tweet_limit']==600 and capacity['new_tweet_used']==sum(r['newTweetBol'] for r in rows),'WATCH_CAPACITY_UNPROVEN')
 excluded={str(x).lower().removeprefix('@')for x in ownership['excluded_handles']}
 require(TARGET not in excluded and profile['x_user_id'] not in ownership['excluded_x_user_ids'],'TARGET_ALPHA_OR_EXCLUDED')
 anchors=0
 for proof in ownership['owned']:
  row=normalized.get(proof['x_handle'].lower())
  require(row is not None and str(row.get('id'))==proof['watch_id'] and proof['flags']=={k:v for k,v in row.items() if k.endswith('Bol')} and proof['groups']=={k:row[k]for k in ('twGroupId','groupName')if k in row},'SHARED_PROVIDER_OWNERSHIP_ANCHOR_CHANGED');anchors+=1
 require(anchors>0,'SHARED_PROVIDER_OWNERSHIP_ANCHOR_MISSING')
 current=normalized.get(TARGET);owner='absent_new_slot_candidate'
 if current:
  require(str(current['id']) not in ownership['excluded_watch_ids'],'TARGET_ALPHA_OR_EXCLUDED')
  matching=[r for r in ownership['owned'] if r['x_handle'].lower()==TARGET and r['watch_id']==str(current['id']) and r['flags']=={k:v for k,v in current.items() if k.endswith('Bol')} and r['groups']=={k:current[k] for k in ('twGroupId','groupName')if k in current}]
  owner='historically_ikun_owned_exact_watch' if len(matching)==1 else 'existing_ownership_unproven_do_not_touch'
 return {'watch_total':len(rows),'legacy_ownership_anchors_matched':anchors,**capacity,'test_handle_already_present':current is not None,'test_watch_ownership':owner,'new_slot_possible':current is None and capacity['available']>0,'current_watch_mutation_allowed':False}


def credential_field(plan):
 field=plan.get('credential_field','OPENNEWS_TOKEN');require(field in ('OPENNEWS_TOKEN','TWITTER_API_TOKEN'),'6551_CREDENTIAL_FIELD_NOT_APPROVED');return field


def credentials_presence(path):
 path=Path(path);exists=path.is_file();result={'file_exists':exists,'values_read':False}
 if exists:
  info=path.lstat();result['private_regular_owned']=stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode) in (0o400,0o600) and not any(p.is_symlink()for p in path.parents)
 return result


def binding(path,expected):
 require(sha(ops.private_file(path))==expected,'PREFLIGHT_PLAN_CHANGED');plan=read_json(path);credential_field(plan)
 require(plan['target']==TARGET and plan['max_provider_attempts']==2 and plan['watch_writes']==0 and plan['new_wss_connections']==0,'PREFLIGHT_SCOPE_CHANGED')
 require(sha(__file__)==plan['tool_source_sha256'],'PREFLIGHT_TOOL_CHANGED')
 for relative,h in plan['helper_files'].items():require(sha(ops.ROOT/relative)==h,'PREFLIGHT_HELPER_CHANGED')
 for p,h in plan['provider_modules'].items():require(sha(ops.private_file(p))==h,'PREFLIGHT_PROVIDER_SOURCE_CHANGED')
 require(sha(ops.private_file(plan['ownership']['path']))==plan['ownership']['sha256'],'PREFLIGHT_OWNERSHIP_CHANGED')
 return plan


async def run(plan,out):
 sys.path.insert(0,plan['tracking_python_root']);sys.path.insert(0,plan['hunter_python_root'])
 import httpx
 from tracking.config import Config
 from tracking.remote import Remote
 from hunterradar.config import read_env
 presence=credentials_presence(plan['credential_source']);require(presence.get('private_regular_owned'),'PRIVATE_CREDENTIAL_SOURCE_REQUIRED')
 before=ops.peers(ops.TrackingOps(None),plan['peer_plan']);ops.TrackingOps(None).ready();baseline=before['alpha']['reconnects']
 require(os.environ.get('IKUN_TRACKING_EXTERNAL_IO_DISABLED')!='1','PREFLIGHT_CHILD_ENV_CLOSED')
 values=read_env(Path(plan['credential_source']));token=values.get(credential_field(plan));require(token,'6551_CREDENTIAL_FIELD_MISSING')
 previous=os.environ.get('IKUN_TRACKING_6551_TOKEN');os.environ['IKUN_TRACKING_6551_TOKEN']=token
 remote=Remote(Config(remote_enabled=True,dedicated_account=False,adopt_only=True,request_interval=.5),transport=httpx.AsyncHTTPTransport(retries=0,trust_env=False));captured={};step=None;attempts=[]
 async def capture(response):
  raw=await response.aread();require(len(raw)<=2_000_000,'PROVIDER_RESPONSE_TOO_LARGE');p=out/(step+'.raw.json');atomic(p,raw);captured[step]={'http_status':response.status_code,'body':json.loads(raw),'artifact':artifact(p)}
 remote.client.event_hooks['response']=[capture]
 def guard():
  result=ops.peers(ops.TrackingOps(None),plan['peer_plan']);require(result['alpha']['reconnects']==baseline,'ALPHA_RECONNECTED_STOP_PREFLIGHT')
 async def read(endpoint,call):
  nonlocal step
  guard();require(endpoint not in attempts and len(attempts)<2,'PREFLIGHT_ATTEMPT_ALREADY_CONSUMED');step=endpoint;attempts.append(endpoint);atomic(out/(endpoint+'.intent.json'),{'endpoint':endpoint,'target':TARGET if endpoint=='twitter_user_info' else None,'started_at':utc(),'attempt':1});value=await call();require(captured[endpoint]['http_status']==200,'PREFLIGHT_HTTP_STATUS_REJECTED');guard();return value
 try:
  async with asyncio.timeout(MAX_SECONDS):
   await read('twitter_user_info',lambda:remote.profile(TARGET));profile=identity(captured['twitter_user_info']['body'])
   watches=await read('twitter_watch',remote.watches);watch=watch_result(captured['twitter_watch']['body'],watches,remote.account_capacity,read_json(plan['ownership']['path']),profile)
   result={'state':'PASS_TWO_READONLY_PREFLIGHT_READS','profile':profile,'watch':watch,'provider_attempts':len(attempts),'attempted_endpoints':attempts,'response_artifacts':{k:v['artifact']for k,v in captured.items()},'credentials_present':True,'credential_values_saved':False,'Watch_writes':0,'new_wss_connections':0,'runtime_database_connections':0,'native_actions':0,'no_automatic_retry':True,'next_setup_not_authorized_by_this_receipt':True};atomic(out/'result.private.json',result)
   return {'state':result['state'],'provider_attempts':2,'followers':profile['followers'],'hunter_mode':profile['hunter_mode'],'watch_total':watch['watch_total'],'new_tweet_used':watch['new_tweet_used'],'new_slot_possible':watch['new_slot_possible'],'existing_watch':watch['test_handle_already_present'],'receipt':str(out/'result.private.json'),'sha256':sha(out/'result.private.json'),'Watch_writes':0,'new_wss_connections':0}
 except BaseException as error:
  atomic(out/'failure.private.json',{'state':'PREFLIGHT_STOPPED_NO_RETRY','error_type':type(error).__name__,'provider_attempts':len(attempts),'attempted_endpoints':attempts,'captured_responses':{k:v['artifact']for k,v in captured.items()},'Watch_writes':0,'new_wss_connections':0});raise
 finally:
  await remote.close()
  if previous is None:os.environ.pop('IKUN_TRACKING_6551_TOKEN',None)
  else:os.environ['IKUN_TRACKING_6551_TOKEN']=previous


def main():
 os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256',required=True);parser.add_argument('--candidate');parser.add_argument('--execute',action='store_true');args=parser.parse_args();plan=binding(Path(args.plan),args.plan_sha256)
 if not args.execute:
  print(json.dumps({'state':'LOCAL_DRY_RUN_ONLY','credentials':credentials_presence(plan['credential_source']),'allowed_reads':list(READS),'max_seconds':MAX_SECONDS,'provider_attempts':0,'Watch_writes':0,'new_wss_connections':0,'runtime_database_connections':0}));return
 require(args.candidate and subprocess.check_output(['git','rev-parse','HEAD'],cwd=ops.ROOT,text=True).strip()==args.candidate and not subprocess.check_output(['git','status','--porcelain'],cwd=ops.ROOT,text=True),'PREFLIGHT_EXACT_CLEAN_CANDIDATE_REQUIRED')
 out=private_dir(plan['output']);fd=os.open(out/'execution.started',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
 try:print(json.dumps(asyncio.run(run(plan,out))))
 except BaseException as error:print(json.dumps({'state':'PREFLIGHT_STOPPED_NO_RETRY','error_type':type(error).__name__,'receipt_directory':str(out),'Watch_writes':0,'new_wss_connections':0}));raise SystemExit(1) from None


if __name__=='__main__':main()
