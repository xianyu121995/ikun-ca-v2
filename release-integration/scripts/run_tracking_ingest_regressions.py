#!/usr/bin/env python3
"""Reuse the frozen B3/voice harnesses in fresh evidence directories; no old evidence writes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import accept_b3_site as b3
import accept_voice_site as voice
from c0_test_fixture import ROOT,NODE

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 out=ROOT/'release-integration/.runtime/tracking-ingest'/('regressions-'+str(time.time_ns()));out.mkdir(mode=0o700,parents=True)
 result={'state':'RUNNING','build_id':(ROOT/'apps/website/.next/BUILD_ID').read_text().strip(),'sets':[],'real_sound':False,'real_provider_calls':0}
 try:
  for name,module in [('B3',b3),('voice',voice)]:
   target=out/name;target.mkdir(mode=0o700);source=Path(module.__file__);snapshot=target/'tested-harness.py';snapshot.write_bytes(source.read_bytes());snapshot.chmod(0o400)
   module.OUT=target;module.CHECKS.clear();module.main()
   receipt=next(target.glob('site-acceptance-*.json'));body=json.loads(receipt.read_text());assert body['state'].startswith('PASS')
   row={'name':name,'state':body['state'],'checks':len(body['checks']),'receipt':str(receipt),'receipt_sha256':sha(receipt),'harness_snapshot':str(snapshot),'harness_sha256':sha(snapshot),'output_override':str(target)}
   if name=='B3':row['historical_harness_metadata_note']='The unasserted Projects_tracking_observation_ingest comment is from the original B3 harness. Actual receiver is verified by the separate Next acceptance; this reused harness does not test observation ingest.'
   result['sets'].append(row)
  args=[str(NODE),'--import','tsx','--test','modules/projects/integration/tests/auth-instance.test.mjs']
  auth=subprocess.run(args,cwd=ROOT,env={**os.environ,'PATH':str(NODE.parent)+':/usr/bin:/bin'},capture_output=True,text=True,timeout=45)
  tap=out/'auth-instance.tap';tap.write_text(auth.stdout+auth.stderr);tap.chmod(0o600);assert auth.returncode==0
  result['sets'].append({'name':'separate_Auth_constructor_regression','checks':3,'exit_code':0,'tap':str(tap),'tap_sha256':sha(tap)})
  result['state']='PASS_FROZEN_B3_VOICE_AUTH_REGRESSIONS'
 finally:
  path=out/'regressions.json';path.write_text(json.dumps(result,indent=2)+'\n');path.chmod(0o600);print(json.dumps({'state':result['state'],'receipt':str(path),'sets':[{k:r[k] for k in ('name','checks')} for r in result['sets']]}))

if __name__=='__main__':main()
