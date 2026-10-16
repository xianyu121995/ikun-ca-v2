#!/usr/bin/env python3
"""Receive only the thirteen frozen Projects paths and its exact existing site transform."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SOURCE='6067658d6092e4d046a8691e8f2f93b34c717801'
CONTROL='2c55f927bcbcc0d2b47472d84156ffa38826876b'
BASE='aa51a640a159e4c8f6cdd841a25f4279e73075ba'
SITE_BASE='23d2221bd99ca500cfad5b570eb4589181effd38'
HELPER='modules/projects/integration/website/lib/projects.ts'
TARGET='apps/website/lib/projects.ts'
PATHS=(
 'modules/projects/README.md','modules/projects/TRACKING-INGEST-REPORT.md',
 'modules/projects/candidate/projects_service/service.py',
 'modules/projects/candidate/projects_service/tracking_observations.py',
 'modules/projects/candidate/projects_service/transport.py',
 'modules/projects/candidate/tests/test_tracking_observations.py',
 'modules/projects/integration/README.md','modules/projects/integration/evidence/tracking-ingest-check.json',
 'modules/projects/integration/tests/tracking-ingest.test.mjs',HELPER,
 'modules/projects/protocols/tracking-observations-size-check.json',
 'modules/projects/protocols/tracking-observations-v1.json','modules/projects/protocols/tracking-observations-v1.md',
)

def at(commit,path):
 return subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT,stderr=subprocess.DEVNULL)

def sha(value):return hashlib.sha256(value).hexdigest()

def baseline(path):
 result=subprocess.run(['git','show',BASE+':'+path],cwd=ROOT,capture_output=True)
 return result.stdout if result.returncode==0 else None

def transform(body):
 old=b'const globalState='
 assert body.count(old)==1
 return body.replace(old,b'readPaths.push(/^\\/api\\/v1\\/hunter\\/events$/, /^\\/api\\/v1\\/tracking\\/events$/);\n'+old,1)

def verify():
 frozen=json.loads(at(CONTROL,'docs/progress/tracking-ingest-freeze.json'))
 assert frozen['implementation_commit']==SOURCE and frozen['state']=='website_receiver_accepted_frozen_integration_released'
 changed=subprocess.check_output(['git','diff','--name-only',BASE,SOURCE,'--','modules/projects'],cwd=ROOT,text=True).splitlines()
 assert set(changed)==set(PATHS)
 record=json.loads((ROOT/'release-integration/night/tracking-ingest-receiving.json').read_text())
 assert record['source_commit']==SOURCE and record['control_commit']==CONTROL and set(record['files'])==set(PATHS)
 overrides={}
 for path,row in record['files'].items():
  before=baseline(path);body=at(SOURCE,path)
  assert row['baseline_sha256']==(sha(before) if before is not None else None)
  assert row['sha256']==sha(body)==sha((ROOT/path).read_bytes()),path
  overrides[path]={'sha256':row['sha256'],'source_commit':SOURCE,'control_commit':CONTROL,'baseline_sha256':row['baseline_sha256']}
 evidence=json.loads(at(SOURCE,'modules/projects/integration/evidence/tracking-ingest-check.json'))
 assert len(evidence['inputs'])==55
 for path,expected in evidence['inputs'].items():
  assert sha(at(SOURCE,path))==expected==sha((ROOT/path).read_bytes()),path
 before=at(SITE_BASE,TARGET);assert before==transform(at(BASE,HELPER))
 after=transform(at(SOURCE,HELPER));assert (ROOT/TARGET).read_bytes()==after
 patch=''.join(difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),n=0,fromfile='a/'+TARGET,tofile='b/'+TARGET)).encode()
 row=record['website_mapping'];assert row['baseline_sha256']==sha(before) and row['target_sha256']==sha(after)
 assert row['patch_sha256']==sha(patch) and (ROOT/row['patch_path']).read_bytes()==patch
 overrides[TARGET]={'sha256':sha(after),'source_commit':SOURCE,'control_commit':CONTROL,'baseline_sha256':sha(before)}
 launcher='scripts/start-c0-lite.mjs';before=at(SITE_BASE,launcher);after=(ROOT/launcher).read_bytes()
 if after!=before:
  launcher_row=record['root_launcher'];assert launcher_row['baseline_sha256']==sha(before) and launcher_row['target_sha256']==sha(after)
  patch=''.join(difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),n=0,fromfile='a/'+launcher,tofile='b/'+launcher)).encode()
  assert launcher_row['patch_sha256']==sha(patch) and (ROOT/launcher_row['patch_path']).read_bytes()==patch
 return overrides,set(PATHS)|{TARGET},row

def receive():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==SITE_BASE
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip() or subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()=='?? release-integration/scripts/receive_tracking_ingest.py'
 rows={}
 for path in PATHS:
  before=baseline(path);body=at(SOURCE,path);target=ROOT/path
  if target.exists():assert before is not None and target.read_bytes()==before,path
  else:assert before is None,path
  target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
  rows[path]={'baseline_sha256':sha(before) if before is not None else None,'sha256':sha(body)}
 before=(ROOT/TARGET).read_bytes();assert before==at(SITE_BASE,TARGET)==transform(at(BASE,HELPER))
 after=transform(at(SOURCE,HELPER));(ROOT/TARGET).write_bytes(after)
 patch=''.join(difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),n=0,fromfile='a/'+TARGET,tofile='b/'+TARGET)).encode()
 path='release-integration/night/patches/tracking-ingest-site.patch';(ROOT/path).write_bytes(patch)
 row={'source_path':HELPER,'baseline_commit':SITE_BASE,'baseline_sha256':sha(before),'target_sha256':sha(after),'patch_path':path,'patch_sha256':sha(patch),'transform':'retain exact two previously accepted B1 readPaths additions'}
 record={'source_commit':SOURCE,'control_commit':CONTROL,'baseline_commit':BASE,'site_baseline_commit':SITE_BASE,'files':rows,'website_mapping':row,'scope':'website receiver only; frozen workers unchanged'}
 (ROOT/'release-integration/night/tracking-ingest-receiving.json').write_text(json.dumps(record,indent=2)+'\n')
 verify()
 print(json.dumps({'source_commit':SOURCE,'frozen_paths':len(PATHS),'mapped_site_helpers':1,'unchanged_owner_source_inputs_verified':55}))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--receive',action='store_true');args=parser.parse_args()
 if args.receive:receive()
 else:verify();print('TRACKING_INGEST_SOURCE_BINDING_PASS')
