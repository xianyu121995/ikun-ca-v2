#!/usr/bin/env python3
"""Run the unchanged Hunter CLI; original CLI's secret file exists only during execution."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from takeover_backup import require,sha,read_json,atomic,artifact
from takeover_operator import System,JOURNAL
import hunter_directory_maintenance as h
from tracking_only_maintenance import private_file


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--static',required=True);parser.add_argument('--static-sha256',required=True);parser.add_argument('--argv');parser.add_argument('--argv-sha256');parser.add_argument('--window-plan');parser.add_argument('--window-plan-sha256');parser.add_argument('--execute',action='store_true');args=parser.parse_args();require(sha(private_file(args.static))==args.static_sha256,'STATIC_CHANGED');static=read_json(args.static)
 if not args.execute:print(json.dumps({'state':'HUNTER_ORIGINAL_CLI_DRY_RUN_ONLY','provider_calls':0,'runtime_database_connections':0,'temporary_secret_file_created':False,'execution_requires_explicit_ephemeral_secret_file_permission':True}));return
 require(static.get('allow_execution_temporary_secret_file')is True,'EXECUTION_ONLY_SECRET_FILE_PERMISSION_REQUIRED');require(args.argv and args.argv_sha256 and sha(private_file(args.argv))==args.argv_sha256 and args.window_plan and args.window_plan_sha256 and sha(private_file(args.window_plan))==args.window_plan_sha256,'EXACT_LATE_ARGV_AND_WINDOW_REQUIRED');argv=read_json(args.argv);window=read_json(args.window_plan);source=static['hunter_source']
 require(argv[:4]==[source['python'],'-m','hunterradar.sample_only','run'] and argv.count('--secrets-file')==1 and argv.count('--database')==1 and argv[argv.index('--database')+1]==str(h.DATABASE),'ORIGINAL_HUNTER_CLI_REQUIRED');require(window['role']=='hunter'and window['purpose']=='sample'and read_json(JOURNAL)['maintenance_steps'][window['phase']]['window'].get('stopped'),'VERIFIED_HUNTER_STOP_REQUIRED')
 own=h.HunterOps(None);own.fence();h.wait_lease(own);h.peers(own,window['native_plan']);sys.path.insert(0,str(Path(source['code_root'])/'services/hunter-worker/python'));from hunterradar.config import read_env
 values=read_env(private_file(static['credentials_source']));token=values.get('TWITTER_API_TOKEN');rest=values.get('TWITTERAPI_IO_API_KEY');require(token and rest and all(33<=ord(c)<=126 for c in token+rest),'DISTINCT_PROVIDER_CREDENTIALS_REQUIRED')
 record=Path(static['output']).parent/'hunter/sampler.process.private.json';require(not record.exists(),'SAMPLER_ALREADY_RECORDED')
 secret=Path(argv[argv.index('--secrets-file')+1]);require(secret.parent==Path(static['output']).parent/'hunter'and not secret.exists(),'EXACT_NEW_EPHEMERAL_SECRET_PATH_REQUIRED');fd=os.open(secret,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w')as f:f.write('OPENNEWS_TOKEN='+token+'\nTWITTERAPI_IO_API_KEY='+rest+'\n')
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','TZ':'Asia/Shanghai','PYTHONPATH':str(Path(source['code_root'])/'services/hunter-worker/python'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'};child=None
 try:
  child=subprocess.Popen(argv,env=env);process=None
  for _ in range(20):
   process=System(None).process(child.pid)
   if process:break
   if child.poll()is not None:break
   import time;time.sleep(.05)
  require(process is not None,'SAMPLER_PROCESS_IDENTITY_REQUIRED');atomic(record,{'role':'hunter','window_phase':window['phase'],'process':process,'argv_sha256':args.argv_sha256});print(json.dumps({'state':'ORIGINAL_HUNTER_CLI_STARTED','sampler_process_receipt':artifact(record)}),flush=True)
  def stop(*_):
   if child.poll()is None:child.send_signal(signal.SIGTERM)
  signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
  try:code=child.wait(timeout=330)
  except subprocess.TimeoutExpired:
   stop()
   try:code=child.wait(timeout=10)
   except subprocess.TimeoutExpired:raise RuntimeError('SAMPLER_STILL_ALIVE_KEEP_RESIDENT_STOPPED')from None
  require(code==0,'ORIGINAL_HUNTER_CLI_FAILED_RECONCILE_NO_RETRY')
 finally:
  if child is not None and child.poll()is None:
   child.send_signal(signal.SIGTERM)
   try:child.wait(timeout=10)
   except subprocess.TimeoutExpired:pass
  secret.unlink(missing_ok=True)


if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'state':'HUNTER_FINITE_LAUNCH_REJECTED','error_type':type(e).__name__,'no_force_kill':True}));raise SystemExit(1)from None
