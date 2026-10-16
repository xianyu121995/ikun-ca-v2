#!/usr/bin/env python3
"""Mint existing 704 CLI inputs from real late receipts and a stopped-window COPY."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
from takeover_backup import require,private_dir,atomic,artifact,sha,read_json
from takeover_operator import ROOT,V2

LATE=('tracking_snapshot','projects_reconcile','setup_profile','watch_before','watch_creation','watch_request')


def iso(value):return datetime.fromtimestamp(value,timezone.utc).isoformat(timespec='microseconds')


def expected_new_watch(target,before,creation,request):
 require(not any(str(r.get('twAccount',r.get('username',''))).lower()==target for r in before),'TARGET_WATCH_ALREADY_EXISTED_DO_NOT_MODIFY')
 require(request.get('method')=='POST'and request.get('endpoint')=='twitter_watch_add'and isinstance(request.get('root_review_sha'),str)and len(request['root_review_sha'])==40,'APPROVED_ACTUAL_ADD_REQUEST_REQUIRED');body=request['body'];require(body.get('username')==target,'ADD_REQUEST_TARGET_DIFFERS')
 require(creation.get('success')is True and isinstance(creation.get('data'),dict),'REAL_ADD_RECEIPT_INSUFFICIENT');returned=creation['data'];identifier=returned.get('id');require(type(identifier)in(str,int)and str(identifier)not in {str(r['id'])for r in before},'ADD_RECEIPT_NEW_ID_UNPROVEN')
 # Real readback exposes twGroupId, not necessarily groupName; do not invent that ID.
 require('twGroupId'in returned and type(returned['twGroupId'])in(str,int),'ADD_RECEIPT_ASSIGNED_GROUP_UNPROVEN')
 required={k for row in before for k in row if k.endswith('Bol')};flags={k:v for k,v in body.items()if k.endswith('Bol')};flags.update({k:v for k,v in returned.items()if k.endswith('Bol')});require(required<=flags.keys()and all(type(v)is bool for v in flags.values()),'ADD_EXPECTED_FLAGS_INCOMPLETE')
 require(all(returned[k]==body[k]for k in returned if k.endswith('Bol')and k in body),'ADD_RECEIPT_FLAGS_CONFLICT');require(flags.get('newTweetBol')is True and flags.get('newTweetQuoteBol')is True and all(v is False for k,v in flags.items()if k not in('newTweetBol','newTweetQuoteBol')),'NEW_REST_TEST_FLAGS_DIFFERS')
 return {'id':identifier,'twAccount':target,'twGroupId':returned['twGroupId'],**flags}


def readback_evidence(before,creation,request,reconcile):
 require(all(x.get('success')is True for x in (before,creation,reconcile)),'REAL_READBACK_RESPONSE_REQUIRED')
 rows=before.get('data');after=reconcile.get('data');require(isinstance(rows,list)and isinstance(after,list)and before.get('total')==len(rows)and reconcile.get('total')==len(after),'READBACK_COMPLETENESS_UNPROVEN')
 target=request.get('body',{}).get('username');require(target=='0x2a_ikun'and not any(str(r.get('twAccount','')).lower()==target for r in rows),'TARGET_WATCH_ALREADY_EXISTED_DO_NOT_MODIFY')
 matches=[r for r in after if str(r.get('twAccount','')).lower()==target];require(len(matches)==1,'READBACK_TARGET_NOT_UNIQUE');row=matches[0];added=creation.get('data',{})
 require(added.get('success')is True and str(added.get('username','')).lower()==target and str(added.get('groupId'))==str(row.get('twGroupId')),'ADD_READBACK_GROUP_DIFFERS')
 # Existing validator proves new ID, exact approved request and all flags from actual readback.
 expected_new_watch(target,rows,{'success':True,'data':row},request)
 require(sum(r.get('newTweetBol')is True for r in after)<=600,'READBACK_CAPACITY_EXCEEDED')
 return {'contract':'tracking-watch-add-readback-evidence-v2','success':True,'before':before,'add':creation,'request':request,'reconcile':reconcile},row


def mint(static,late):
 source=static['tracking_source'];sys.path.insert(0,str(Path(source['code_root'])/'services/tracking-worker/python'))
 from tracking.new_test import NewAuthorization,NewProof,ProjectsReconcileEnvelope,Exclusions
 from tracking.sample import AlphaState
 from tracking.protocol import Command
 from tracking.takeover import private_path,read_private,digest
 from tracking.events import timestamp
 require((source['source_commit']=='704e6214ba7b2dff79ec372249bf47e2b9eb7c04' or (static.get('sample_proof_version')==2 and source['source_commit']=='b728f1e990896133359e89b5c5a9d1bad793bfce')),'FROZEN_TRACKING_SAMPLE_REQUIRED')
 require('watch_after'not in late,'SETUP_MUST_NOT_CONSUME_OBSERVATION_WATCH_READ')
 require(all(k in late for k in LATE) and all(k in late for k in ('identity_observed_at','watch_created_at','approved_at','create_command_id')),'ACTUAL_LATE_RECEIPTS_REQUIRED')
 def data(key):
  row=late[key];return read_private(row['path'],row['sha256'])
 projects=ProjectsReconcileEnvelope.model_validate(data('projects_reconcile'));record=projects.data.result
 if projects.data.contract=='projects-home-v1':record=record['project']
 project_id=record['project_id'];profile=data('setup_profile');require(profile.get('success')is True and profile['data'].get('screenName','').lower()==static['target'],'PROFILE_TARGET_DIFFERS');user_id=profile['data']['userId']
 snap=private_path(late['tracking_snapshot']['path']);require(ROOT/'release-integration/.runtime' in snap.parents and V2 not in snap.parents and sha(snap)==late['tracking_snapshot']['sha256'],'STOPPED_COPY_REQUIRED_NOT_LIVE_DB')
 with closing(sqlite3.connect(snap.as_uri()+'?mode=ro',uri=True)) as db:
  db.execute('PRAGMA query_only=ON');db.row_factory=sqlite3.Row;require(db.execute('PRAGMA user_version').fetchone()[0]==4 and db.execute('PRAGMA application_id').fetchone()[0]==0x494B0202,'TRACKING_COPY_SCHEMA_DIFFERS')
  row=db.execute('SELECT * FROM projects WHERE project_id=?',(project_id,)).fetchone();require(row is not None,'REAL_NEW_SUBSCRIPTION_REQUIRED');row=dict(row)
  command=db.execute('SELECT * FROM commands WHERE command_id=?',(late['create_command_id'],)).fetchone();require(command is not None,'REAL_CREATE_COMMAND_REQUIRED');command=dict(command)
  require(db.execute('SELECT heartbeat FROM runtime WHERE id=1').fetchone()[0]==0,'COPY_NOT_FROM_RELEASED_WINDOW')
 value=Command.model_validate_json(command['envelope']);require(value.operation=='tracking.create' and value.actor.role=='superadmin' and value.payload.get('confirmed')is True and value.project_id==row['project_id'] and value.payload.get('x_user_id')==user_id and value.payload.get('x_handle','').lower()==static['target'],'REAL_BFF_CREATION_UNPROVEN')
 require(row['handle']==static['target'] and row['x_user_id']==user_id and row['generation']==row['revision']==1 and command['subscription_id']==row['subscription_id'],'NEW_SUBSCRIPTION_IDENTITY_DIFFERS')
 def watches(key):
  envelope=data(key);require(envelope.get('success')is True,'REAL_WATCH_RESPONSE_REQUIRED');rows=envelope['data'];rows=rows if isinstance(rows,list)else rows.get('list',rows.get('items'));require(isinstance(rows,list),'WATCH_LIST_REQUIRED');return rows
 before=watches('watch_before');version2='watch_reconcile'in late
 if version2:
  require(static.get('sample_proof_version')==2,'EXPLICIT_V2_STATIC_REQUIRED')
  from tracking.new_test import NewProofV2
  evidence,watch=readback_evidence(data('watch_before'),data('watch_creation'),data('watch_request'),data('watch_reconcile'))
  evidence_path=private_dir(static['output'])/'watch-add-readback-evidence-v2.json';require(not evidence_path.exists(),'READBACK_EVIDENCE_ALREADY_EXISTS');atomic(evidence_path,evidence);creation_artifact=artifact(evidence_path)
 else:watch=expected_new_watch(static['target'],before,data('watch_creation'),data('watch_request'));creation_artifact=late['watch_creation']
 negative=Exclusions.model_validate(read_private(static['exclusions'],sha(private_path(static['exclusions']))));require(static['target']not in {x.lower()for x in negative.excluded_handles}and user_id not in negative.excluded_x_user_ids and str(watch['id'])not in negative.excluded_watch_ids,'TEST_ACCOUNT_EXCLUDED')
 initial=private_path(static['alpha_initial']);alpha=AlphaState.model_validate(read_private(initial,sha(initial)));expected_exclusions=digest({'handles':sorted({x.lower()for x in negative.excluded_handles}),'watch_ids':sorted(negative.excluded_watch_ids),'x_user_ids':sorted(negative.excluded_x_user_ids)});require(alpha.healthy and alpha.exclusions_sha256==expected_exclusions,'ALPHA_INITIAL_DIFFERS')
 clocks=[timestamp(x)for x in (late['identity_observed_at'],late['watch_created_at'],late['approved_at'],record['created_at'],projects.data.completed_at)]+[row['created_at']];now=time.time();require(all(x is not None and -1<=now-x<240 for x in clocks),'LATE_FACTS_ALREADY_TOO_OLD');seconds=min(static['max_tracking_seconds'],int(min(clocks)+295-now));require(seconds>=30,'INSUFFICIENT_FRESH_SAMPLE_WINDOW')
 approved=timestamp(late['approved_at']);require(approved>=max(clocks[:2]+[row['created_at']]),'ACTUAL_FINAL_APPROVAL_REQUIRED')
 proof={'contract':'tracking-new-test-account-proof-v1','origin':'new-test-account','authorization_id':static['tracking_authorization_id'],**{k:row[k]for k in ('project_id','subscription_id','x_user_id','generation','revision')},'x_handle':static['target'],'subscription_created_at':iso(row['created_at']),'create_command_id':command['command_id'],'create_command_body_sha256':command['body_hash'],'approved_at':late['approved_at'],'identity_observed_at':late['identity_observed_at'],'projects_creation_receipt_sha256':late['projects_reconcile']['sha256'],'projects_create_idempotency_key':projects.data.idempotency_key,'projects_create_original_request_id':projects.data.original_request_id,'projects_create_contract':projects.data.contract,'projects_create_completed_at':projects.data.completed_at,'setup_profile_sha256':late['setup_profile']['sha256'],'operator_watch_creation_evidence_sha256':late['watch_creation']['sha256'],'operator_watch_created_at':late['watch_created_at'],'operator_new_owned_watch':True,'watch_id':str(watch['id']),'groups':{k:watch[k]for k in ('twGroupId','groupName')if k in watch},'flags':{k:v for k,v in watch.items()if k.endswith('Bol')},'setup_profile_attempts':1,'setup_watch_read_attempts':1,'setup_watch_write_attempts':1};proof.update(contract='tracking-new-test-account-proof-v2',setup_watch_read_attempts=2,operator_watch_creation_evidence_sha256=creation_artifact['sha256']) if version2 else None;proof=(NewProofV2 if version2 else NewProof).model_validate(proof).model_dump()
 out=private_dir(static['output']);require(not (out/'authorization.json').exists()and not (out/'proof.json').exists(),'LATE_AUTHORIZATION_ALREADY_MINTED');atomic(out/'proof.json',proof)
 authorization={'contract':'tracking-sample-new-test-v1','execution_id':'IKUN-ONLY-2026-10-16','authorization_id':static['tracking_authorization_id'],'candidate_commit':source['source_commit'],'source_set_sha256':source['fingerprint']['source_set_sha256'],'issued_at':iso(now),'expires_at':iso(now+seconds),'max_seconds':seconds,**{k:row[k]for k in ('project_id','subscription_id','x_user_id','generation','revision')},'x_handle':static['target'],'alpha_initial_sha256':sha(initial),'new_test_proof_sha256':sha(out/'proof.json'),'projects_creation_receipt_sha256':late['projects_reconcile']['sha256'],'setup_profile_sha256':late['setup_profile']['sha256'],'exclusions_sha256':sha(private_path(static['exclusions']))};authorization=NewAuthorization.model_validate(authorization).model_dump();atomic(out/'authorization.json',authorization)
 argv=[source['python'],str(Path(source['code_root'])/'services/tracking-worker/python/integration/sample-tracking.py'),'--config',static['config'],'--authorization',str(out/'authorization.json'),'--authorization-sha256',sha(out/'authorization.json'),'--alpha-state',static['alpha_rolling'],'--alpha-initial-state',static['alpha_initial'],'--new-test-proof',str(out/'proof.json'),'--projects-creation-receipt',late['projects_reconcile']['path'],'--setup-profile',late['setup_profile']['path'],'--watch-creation-receipt',creation_artifact['path'],'--exclusions',static['exclusions'],'--execute','--serve'];atomic(out/'original-cli-argv.private.json',argv)
 return {'state':'LATE_TRACKING_INPUTS_MINTED_NOT_EXECUTED','seconds':seconds,'proof':artifact(out/'proof.json'),'authorization':artifact(out/'authorization.json'),'argv':artifact(out/'original-cli-argv.private.json'),'provider_calls':0,'runtime_database_connections':0,'snapshot_connections':1}


if __name__=='__main__':
 import os
 os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--static',required=True);parser.add_argument('--static-sha256',required=True);parser.add_argument('--late');parser.add_argument('--late-sha256');parser.add_argument('--mint',action='store_true');args=parser.parse_args();require(sha(Path(args.static))==args.static_sha256,'STATIC_INPUTS_CHANGED');static=read_json(args.static)
 if not args.mint:print(json.dumps({'state':'WAIT_REAL_LATE_RECEIPTS_NO_AUTHORIZATION_CREATED','required_artifacts':list(LATE),'provider_calls':0,'runtime_database_connections':0,'maximum_observation_seconds':static['max_tracking_seconds']}))
 else:
  require(args.late and args.late_sha256 and sha(Path(args.late))==args.late_sha256,'REAL_LATE_INPUT_HASH_REQUIRED')
  try:print(json.dumps(mint(static,read_json(args.late))))
  except Exception as e:print(json.dumps({'state':'LATE_INPUTS_REJECTED','error_type':type(e).__name__,'provider_calls':0}));raise SystemExit(1)from None
