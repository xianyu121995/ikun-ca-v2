#!/usr/bin/env python3
"""Thin reuse of the accepted stop/backup/restore helpers; never runs a sampler or API."""
import argparse
import copy
import json
import os
from pathlib import Path
import plistlib
import sys
import uuid
from takeover_backup import require,private_dir,atomic,artifact,sha,read_json,sqlite_backup,copy_private
from takeover_operator import Journal,original_absent,same_process
from projects_first_maintenance import stop_web_once
import tracking_only_maintenance as t
import hunter_directory_maintenance as h


def prepare(role,purpose,static,path):
 require(role in ('hunter','tracking')and purpose in ('setup','sample'),'EXACT_DOMAIN_PURPOSE_REQUIRED');require(not path.exists(),'NEW_WINDOW_PLAN_REQUIRED');private_dir(path.parent)
 peer=copy.deepcopy(read_json(static['tracking_peer_plan']));tracking=t.TrackingOps(None);hunter=h.HunterOps(None)
 for name,ops,label,expected in (('v2_Tracking',tracking,t.LABEL,t.expected_job()),('v2_Hunter',hunter,h.LABEL,h.expected_job())):
  plist=Path.home()/'Library/LaunchAgents'/(label+'.plist');require(plistlib.loads(t.private_file(plist).read_bytes())==expected,'RESIDENT_PLIST_CHANGED');job=ops.job();require(job['loaded']and job['pid'],'RESIDENT_NOT_RUNNING');current=ops.process(job['pid']);require(current and current['cwd']==str(t.V2/'jobs'/('tracking'if name=='v2_Tracking'else'hunter')),'RESIDENT_CWD_CHANGED');peer['protection']['protected_processes'][name]=current
 t.peers(tracking,peer);tracking.ready();own=hunter if role=='hunter'else tracking;current=peer['protection']['protected_processes'].pop('v2_Hunter'if role=='hunter'else'v2_Tracking');module=h if role=='hunter'else t;native=read_json(h.OUTPUT/'execution-plan-v5-stopped-window.json')if role=='hunter'else read_json(t.OUTPUT/'execution-plan-v2.json');native['initial_plist_sha256']=sha(module.PLIST)
 if role=='hunter':native['during_protection']=peer['protection']
 else:native['protection']=peer['protection']
 out=private_dir(path.parent/('window-'+role+'-'+uuid.uuid4().hex));plan={'role':role,'purpose':purpose,'phase':'finite-window:'+role+':'+out.name,'resident_process':current,'resident_tree':own.tree(current['pid']),'peer':peer,'native_plan':native,'output':str(out),'tool_sha256':sha(__file__),'operation_helpers':{str(Path(h.__file__)):sha(Path(h.__file__)),str(Path(t.__file__)):sha(Path(t.__file__))}};atomic(path,plan);print({'state':'WINDOW_PREPARED_ONLY','plan':str(path),'sha256':sha(path),'native_actions':0})


def operate(path,expected,action,sampler):
 require(sha(t.private_file(path))==expected,'WINDOW_PLAN_CHANGED');plan=read_json(path);require(plan['tool_sha256']==sha(__file__),'WINDOW_TOOL_CHANGED')
 for file,digest in plan['operation_helpers'].items():require(sha(file)==digest,'WINDOW_OPERATION_HELPER_CHANGED')
 role=plan['role'];module=h if role=='hunter'else t;own=module.HunterOps(None)if role=='hunter'else module.TrackingOps(None);out=Path(plan['output']);own.log=out/'native.private.log'
 def guard():return h.peers(own,plan['native_plan'])if role=='hunter'else t.peers(own,plan['native_plan'])
 with Journal()as journal:
  state=journal.data.setdefault('maintenance_steps',{}).setdefault(plan['phase'],{'window':{},'schema5_observed':role=='hunter'});window=state['window']
  def save():journal.save()
  def backup(name):
   if name in state:return state[name]
   directory=private_dir(out/name);value={k:sqlite_backup(p,private_dir(directory/k),strict_foreign_keys=True)for k,p in t.DATABASES.items()};state[name]=value;save();return value
  guard()
  if action=='stop':
   if window.get('restored'):raise RuntimeError('WINDOW_ALREADY_RESTORED_NEW_PLAN_REQUIRED')
   backup('before');
   if 'original_plist'not in window:window['original_plist']=copy_private(module.PLIST,out/'resident-original.plist');save()
   protected={p['pid']for p in plan['peer']['protection']['protected_processes'].values()}|{p['pid']for p in plan['peer']['web_tree']};stop_web_once(window,save,own,plan['resident_process'],protected,expected_tree=plan['resident_tree']);own.fence()
   if role=='hunter':h.wait_lease(own)
   else:t.released(t.DATABASE)
   stopped=backup('stopped');print({'state':'OWNED_WRITER_STOPPED_VERIFIED','role':role,'snapshot':stopped[role]['artifact'],'native_actions':'one owned label stop; no sampler/provider calls'})
  else:
   require(window.get('stopped'),'NO_VERIFIED_STOP_WINDOW')
   if plan['purpose']=='sample':
    require(sampler,'ACTUAL_SAMPLER_PROCESS_RECEIPT_REQUIRED');sample=read_json(t.private_file(sampler));require(sample['role']==role and sample.get('window_phase')==plan['phase'] and original_absent(own,sample['process']),'SAMPLER_STILL_ALIVE_NO_RESTORE')
   if not own.job()['loaded']:own.fence()
   after=backup('after');checkpoint=after[role]
   if role=='hunter':h.compatible_restore(state,window,save,own,plan['native_plan'],5,checkpoint=checkpoint)
   else:t.restore(window,save,own,plan['native_plan'],checkpoint)
   guard();print({'state':'FIXED_RESIDENT_HARDOFF_RESTORED','role':role,'new_process':window['new_process'],'snapshot':checkpoint['artifact']})


if __name__=='__main__':
 os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('dry-run','prepare','stop','restore'));parser.add_argument('--role',choices=('hunter','tracking'));parser.add_argument('--purpose',choices=('setup','sample'),default='sample');parser.add_argument('--static');parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256');parser.add_argument('--sampler-process');args=parser.parse_args()
 try:
  if args.action=='dry-run':print({'state':'LOCAL_WINDOW_DRY_RUN_ONLY','role':args.role,'native_actions':0,'provider_calls':0,'runtime_database_connections':0})
  elif args.action=='prepare':require(args.static and args.role,'STATIC_AND_ROLE_REQUIRED');prepare(args.role,args.purpose,read_json(args.static),Path(args.plan))
  else:require(args.plan_sha256,'EXACT_WINDOW_PLAN_HASH_REQUIRED');operate(Path(args.plan),args.plan_sha256,args.action,args.sampler_process)
 except Exception as e:print({'state':'WINDOW_STOPPED_NO_BLIND_RETRY','error_type':type(e).__name__});raise SystemExit(1)from None
