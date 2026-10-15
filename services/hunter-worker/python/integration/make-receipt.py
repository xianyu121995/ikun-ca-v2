"""Bind local evidence and exact owned source mappings; no services or provider IO."""
import gzip,hashlib,json,re,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET

MODULE=Path(__file__).resolve().parents[1];ROOT=MODULE.parents[2];E=MODULE/'docs/b4'
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(path):return json.loads(path.read_text())
prior=read(E/'receipt.json');protected=prior['protected_untracked_files_sha256']
assert len(protected)==12
for name,checksum in protected.items():assert sha(ROOT/name)==checksum,name
suite=list(ET.parse(E/'python-night-final.xml').getroot().iter('testsuite'))
python={k:sum(int(x.get(k,'0')) for x in suite) for k in ('tests','failures','errors','skipped')}
assert python=={'tests':227,'failures':0,'errors':0,'skipped':0},python
tap=(E/'auth-route-night.tap').read_text()
node={key:int(re.search(r'^# '+label+r' (\d+)$',tap,re.M)[1]) for key,label in [('tests','tests'),('passed','pass'),('failed','fail')]}
assert node=={'tests':10,'passed':10,'failed':0}
final=read(E/'final-batch.json');assert final['same_source_entire_batch'] and final['status']=='passed'
for name,checksum in final['source_files_sha256'].items():assert sha(ROOT/name)==checksum,name
assert len(final['formal_browser']['passed'])==14 and len(final['legacy_browser']['passed'])==11
assert final['restore_kill']['kill_cases']==5 and final['process']['starts']==3
build=read(MODULE/'var/b4/evidence/build.json')
for name,checksum in build['candidate_files_sha256'].items():assert sha(MODULE/name)==checksum,name
assert build['ui_patch_sha256']==sha(MODULE/'integration/patches/hunter-live.patch')
coord=Path('/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/var/coordination')
for path in coord.glob('hunter-worker-*.json'):shutil.copyfile(path,E/'locks'/path.name)
shutil.copyfile(MODULE/'var/b4/evidence/build.json',E/'build-night.json')
raw=(MODULE/'var/b4/evidence/build.log').read_bytes()
(E/'build-night-original.log.gz').write_bytes(gzip.compress(raw,mtime=0))
(E/'build-night.txt').write_text('\n'.join(line.rstrip() for line in raw.decode().splitlines()).rstrip()+'\n')
receiving=[]
def mapping(path,target,kind):receiving.append({'source':str(path.relative_to(ROOT)),'sha256':sha(path),'target':target,'kind':kind})
for path in sorted((MODULE/'hunterradar').glob('*.py')):mapping(path,str(path.relative_to(ROOT)),'runtime')
for path in sorted((ROOT/'schemas/hunter').glob('*.sql')):mapping(path,str(path.relative_to(ROOT)),'explicit_migration')
mapping(ROOT/'services/hunter-worker/src/main.ts','services/hunter-worker/src/main.ts -> dist/main.js','compiled_entry')
for path in sorted((MODULE/'integration/website').rglob('*')):
    if path.is_file():mapping(path,'apps/website/'+str(path.relative_to(MODULE/'integration/website')),'website_candidate')
mapping(MODULE/'integration/patches/hunter-live.patch','apply --check against Hunter UI 08065d7; App.tsx + model.ts only','reviewed_patch')
mapping(MODULE/'requirements-lock.txt','private Python>=3.11 venv dependency installation only','dependency_lock')
requirements=sha(MODULE/'requirements-lock.txt')
receipt={'record_version':2,'stage':'B4-night-final-local','state':'implementation_complete_pending_chief_freeze','accepted_by_chief':False,
 'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'baseline_implementation_commit':'bd69bbd0bba6fdc4f7c66191a839612dd53989d6',
 'protocol_commit':'b16fb36a8b8269350319c02a60faa6ea2708d95a','approval_commit':'579a57f2e3e470525eb53f9f1f85ba75d25f3728',
 'product_commit':'50ee277aed435a723aab6139bd952e709b3ad08e','source_commit_binding':'Git commit containing this manifest; B4-DELIVERY.md records implementation full SHA after commit',
 'pins':build['pins'],'python':python,'node':node,'formal_browser_groups':14,'legacy_browser_groups':11,'main_process_starts':3,'restore_sigkill_boundaries':5,
 'nested_counts_added_twice':False,'historical_69_included_in_python':True,'old_130_included_in_python':True,
 'requirements_lock_sha256':requirements,'python_version':sys.version.split()[0],
 'source_files_sha256':final['source_files_sha256'],'protected_ui_files_sha256':protected,
 'receiving_manifest':'integration/RECEIVING-B4.json','checks':{'same_source_final_batch':'PASS','ui_12_hashes':'PASS','root_or_other_module_source_modified':False},
 'decisions':{key:{'status':'PASS_local_fixture','evidence':['python-night-final.xml','final-batch.json','restore-kill.json','browser/results.json']} for key in ('DEC-D3','DEC-D4','DEC-D5','DEC-C04','B4-R1','B4-R2','B4-R3','B4-R4')},
 'path_lstat_preventive_fix':{'regressions':2,'observed_production_failure_claimed':False},
 'commands':[
  '.venv/bin/python -m pytest -q --tb=short --junitxml=docs/b4/python-night-final.xml',
  'node integration/tests/prepare-light.mjs',
  'node --test --test-reporter=tap integration/tests/guards.test.mjs > docs/b4/auth-route-night.tap',
  'node integration/tests/typecheck-light.mjs > docs/b4/typecheck-night.txt',
  'python3 <main>/scripts/with-heavy-lock.py --owner hunter-worker --timeout 600 -- .venv/bin/python integration/build-preview.py',
  'B4_NODE=<Node24> HUNTER_PLAYWRIGHT_MODULE=<installed playwright> python3 <main>/scripts/with-heavy-lock.py --owner hunter-worker --timeout 600 -- .venv/bin/python scripts/final_batch_b4.py'],
 'heavy_lock_receipts':[str(p.relative_to(E)) for p in sorted((E/'locks').glob('*.json'))],
 'external_provider_calls':0,'shared_watch_modified':False,'other_business_db_opened_by_hunter':False,'merge_push_deploy':False,
 'unverified':['real 6551/REST/paid sources','actual Projects IPC -> Tracking / 600-capacity full chain','C0 multi-source gateway composition and protected-site deployment','OS separate-user permissions isolation','reliable follow time policy remains undecided; disclosed existing source strategy'],
 'evidence_sha256':{str(p.relative_to(E)):sha(p) for p in sorted(E.rglob('*')) if p.is_file() and p.name not in ('night-receipt.json','receipt.json')}}
delivery={'record_version':1,'state':'candidate_pending_chief_freeze','pins':build['pins'],'protocol_approval_commit':receipt['approval_commit'],
 'files':receiving,'schema_version':4,'sql_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'schemas/hunter').glob('*.sql'))},
 'ui_patch_base_commit':build['pins']['hunter_ui'],'ui_patch_sha256':build['ui_patch_sha256'],'patched_ui_output_sha256':build['patched_ui_files_sha256'],
 'projects_helper_sha256':build['projects_helper_sha256'],'python_requirements_lock_sha256':requirements,
 'pnpm_lock_sha256':sha(ROOT/'pnpm-lock.yaml'),'hunter_package_sha256':sha(ROOT/'services/hunter-worker/package.json'),
 'compiled_entry_sha256':sha(ROOT/'services/hunter-worker/dist/main.js'),
 'external_io_required':False,'internal_project_delivery_separate':True,'requires_private_cwd_without_dotenv':True,
 'excluded':['services/hunter-worker/ui/**','var/**','.env','node_modules','venv','.next','preview-only action probe','fixture accounts/databases','test-only gateway mounts'],
 'shared_gateway_contributions_only':['hunterCommandRoute','hunterEventsRoute'],'runbook':'README-B4.md'}
(MODULE/'integration/RECEIVING-B4.json').write_text(json.dumps(delivery,ensure_ascii=False,indent=2)+'\n')
(E/'night-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'python':python,'node':node,'formal_browser_groups':14,'legacy_browser_groups':11,'main_starts':3,'restore_sigkill':5,'mapped_files':len(receiving),'protected_ui':12},ensure_ascii=False))
