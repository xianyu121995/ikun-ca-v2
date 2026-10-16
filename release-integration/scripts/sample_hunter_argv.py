#!/usr/bin/env python3
"""Bind real late owner artifacts to the unchanged finite Hunter CLI; never mint fake proofs."""
import argparse
import hashlib
import json
from pathlib import Path
from takeover_backup import require,sha,read_json,atomic,private_dir,artifact
from takeover_operator import V2

REQUIRED=('manifest','gates','tracking_evidence','alpha_evidence','source_manifest','projects_evidence','setup_evidence')


def bind(static,index):
 require(all(k in index for k in REQUIRED),'REAL_HUNTER_OWNER_ARTIFACTS_REQUIRED');values={}
 for key in REQUIRED:
  proof=index[key];require(sha(Path(proof['path']))==proof['sha256'],'HUNTER_INPUT_HASH_DIFFERS');values[key]=read_json(proof['path'])
 canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
 digest=lambda x:hashlib.sha256(canonical(x)).hexdigest()
 require(values['manifest']['protocol']=='hunter-sample-only-v2' and values['manifest']['run_id']==static['hunter_run_id'] and values['gates']['manifest_sha256']==digest(values['manifest']),'OWNER_MANIFEST_GATE_BINDING_DIFFERS')
 require(values['gates']['sample_source_sha256']==static['hunter_source']['fingerprint']['sample_source_sha256'] and len(values['manifest']['hunters'])==2,'HUNTER_FROZEN_SOURCE_DIFFERS')
 modes={x['mode']for x in values['manifest']['hunters']};require(modes=={'REST','WSS'} and any(x['mode']=='REST' and x['x_handle']==static['target'] and x['rest_phase']=='baseline_only' for x in values['manifest']['hunters']),'ACTUAL_REST_TEST_AND_ONE_WSS_REQUIRED')
 out=private_dir(Path(static['output']).parent/'hunter');require(not (out/'manifest.json').exists()and not (out/'gates.json').exists(),'HUNTER_LATE_INPUTS_ALREADY_BOUND');atomic(out/'manifest.json',canonical(values['manifest']));atomic(out/'gates.json',canonical(values['gates']))
 argv=[static['hunter_source']['python'],'-m','hunterradar.sample_only','check','--database',str(V2/'data/hunter/hunter.db'),'--manifest',str(out/'manifest.json'),'--manifest-sha256',sha(out/'manifest.json'),'--gates',str(out/'gates.json'),'--gates-sha256',sha(out/'gates.json'),'--alpha-guard',str(Path(static['alpha_initial']).parent/'hunter.guard.json')]
 for name in ('tracking_evidence','alpha_evidence','source_manifest','projects_evidence','setup_evidence'):argv+=['--'+name.replace('_','-'),index[name]['path']]
 atomic(out/'original-check-argv.private.json',argv);run=list(argv);run[3]='run';run+=['--offline-confirmed','--secrets-file',str(out/'execution-only-secrets.env')];atomic(out/'original-run-argv.private.json',run)
 return {'state':'REAL_HUNTER_ARTIFACTS_BOUND_NOT_EXECUTED','check_argv':artifact(out/'original-check-argv.private.json'),'run_argv':artifact(out/'original-run-argv.private.json'),'temporary_secrets_materialized':False,'runtime_database_connections':0,'provider_calls':0}


if __name__=='__main__':
 import os
 os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--static',required=True);parser.add_argument('--static-sha256',required=True);parser.add_argument('--index');parser.add_argument('--index-sha256');parser.add_argument('--bind',action='store_true');args=parser.parse_args();require(sha(Path(args.static))==args.static_sha256,'STATIC_CHANGED');static=read_json(args.static)
 if not args.bind:print(json.dumps({'state':'WAIT_REAL_HUNTER_LATE_ARTIFACTS','required':list(REQUIRED),'runtime_database_connections':0,'provider_calls':0,'fence_reset_allowed':False}))
 else:
  require(args.index and args.index_sha256 and sha(Path(args.index))==args.index_sha256,'LATE_INDEX_HASH_REQUIRED')
  try:print(json.dumps(bind(static,read_json(args.index))))
  except Exception as e:print(json.dumps({'state':'HUNTER_LATE_INPUTS_REJECTED','error_type':type(e).__name__,'provider_calls':0}));raise SystemExit(1)from None
