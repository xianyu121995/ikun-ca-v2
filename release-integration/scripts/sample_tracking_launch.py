#!/usr/bin/env python3
"""Fence the resident writer, then exec the ORIGINAL finite 704 CLI with memory-only keys."""
import argparse
import json
import os
from pathlib import Path
import sys
from takeover_backup import require,sha,read_json
import tracking_only_maintenance as ops
from takeover_operator import System,JOURNAL
from takeover_backup import atomic,artifact


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--static',required=True);parser.add_argument('--static-sha256',required=True);parser.add_argument('--argv');parser.add_argument('--argv-sha256');parser.add_argument('--window-plan');parser.add_argument('--window-plan-sha256');parser.add_argument('--execute',action='store_true');args=parser.parse_args();require(sha(ops.private_file(args.static))==args.static_sha256,'STATIC_BINDING_CHANGED');static=read_json(args.static)
 if not args.execute:
  print(json.dumps({'state':'FINITE_CLI_LAUNCH_DRY_RUN_ONLY','source_commit':static['tracking_source']['source_commit'],'config_file_exists':Path(static['config']).is_file(),'late_argv_file_exists':bool(args.argv and Path(args.argv).is_file()),'resident_stop_required':True,'provider_calls':0,'runtime_database_connections':0,'native_actions':0}));return
 require(args.argv and args.argv_sha256 and sha(ops.private_file(args.argv))==args.argv_sha256,'MINTED_ARGV_HASH_REQUIRED');argv=read_json(args.argv);source=static['tracking_source'];expected=Path(source['code_root'])/'services/tracking-worker/python/integration/sample-tracking.py'
 require((source['source_commit']=='704e6214ba7b2dff79ec372249bf47e2b9eb7c04' or (static.get('sample_proof_version')==2 and source['source_commit']=='b728f1e990896133359e89b5c5a9d1bad793bfce')) and argv[:2]==[source['python'],str(expected)] and argv.count('--config')==1 and argv[argv.index('--config')+1]==static['config'] and argv[-2:]==['--execute','--serve'],'ORIGINAL_FINITE_CLI_REQUIRED')
 require(args.window_plan and args.window_plan_sha256 and sha(ops.private_file(args.window_plan))==args.window_plan_sha256,'ACTUAL_WINDOW_PLAN_REQUIRED');window=read_json(args.window_plan);require(window['role']=='tracking'and window['purpose']=='sample'and read_json(JOURNAL)['maintenance_steps'][window['phase']]['window'].get('stopped'),'VERIFIED_STOP_WINDOW_REQUIRED')
 own=ops.TrackingOps(None);own.fence();ops.released(ops.DATABASE)
 ops.peers(own,window['native_plan'])
 sys.path.insert(0,str(Path(static['hunter_source']['code_root'])/'services/hunter-worker/python'));from hunterradar.config import read_env
 values=read_env(ops.private_file(static['credentials_source']));token=values.get('TWITTER_API_TOKEN');require(token,'6551_VERIFIED_ALIAS_MISSING')
 native=read_json(ops.private_file(static['native_environment_file']));env={k:v for k,v in native.items()if k in ('DATA_ROOT','TRACKING_API_TOKEN')};require(env.get('DATA_ROOT')==str(ops.V2/'data')and env.get('TRACKING_API_TOKEN'),'ORIGINAL_DIRECTION_CREDENTIAL_REQUIRED')
 env.update(PATH='/usr/bin:/bin',LANG='en_US.UTF-8',TZ='Asia/Shanghai',PYTHONPATH=str(Path(source['code_root'])/'services/tracking-worker/python'),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',IKUN_TRACKING_6551_TOKEN=token)
 # Only this finite child receives provider access. The unloaded resident's private env/config stay hard-off.
 process=System(None).process(os.getpid());require(process is not None,'SAMPLER_PROCESS_IDENTITY_REQUIRED');record=Path(static['output'])/'sampler.process.private.json';require(not record.exists(),'SAMPLER_PROCESS_ALREADY_RECORDED');atomic(record,{'role':'tracking','window_phase':window['phase'],'process':process,'argv_sha256':args.argv_sha256});print(json.dumps({'state':'EXEC_ORIGINAL_FINITE_CLI','sampler_process_receipt':artifact(record)}),flush=True)
 os.execve(source['python'],argv,env)


if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'state':'FINITE_LAUNCH_REJECTED','error_type':type(e).__name__,'new_connections_by_launcher':0}));raise SystemExit(1)from None
