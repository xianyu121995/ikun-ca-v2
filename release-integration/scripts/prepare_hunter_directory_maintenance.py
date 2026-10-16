#!/usr/bin/env python3
"""Freeze the F9 Hunter reader and CURRENT protection projection. No execute mode."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from contextlib import closing
import urllib.request

from takeover_backup import require,sha,private_dir,atomic,artifact,read_json,validate_artifacts,utc
from takeover_operator import ROOT,V2,PLAN as LEGACY_PLAN,System,guard,same_process
from projects_first_maintenance import WebOps
import night_worker_ops as night

SOURCE='f9e3c6cbf7c44676c37ef973389e6176777640ce'
PROJECTS=ROOT/'release-integration/.runtime/v2-maintenance/projects-first/09af-5afc-v1/final-receipt.json'
PROJECTS_SHA='bd437fb7dee3c99bf651aa38eede5daa11055c2084f1f068397aa4ef86a715c2'
INTAKE=ROOT/'release-integration/.runtime/v2-maintenance/hunter-directory-rehearsal/intake-1792150068812437000/INTAKE-ONLY.json'
INTAKE_SHA='8746c5d82dcf70efb4242aab3502c88722ea42e3947a2ab105e3d74dcb1f2b95'
REHEARSAL=ROOT/'release-integration/.runtime/v2-maintenance/hunter-directory-rehearsal/clone-1792150656666089000/REHEARSAL_ONLY.json'
REHEARSAL_SHA='e9af5e71f832003cfe51c9d730a701a773a13686b168dd22a8a327db9c3ee18a'
PACKAGE=ROOT.parent/'hunter-worker/var/directory-v2-final-8f5a453a/directory-package-v2-for-root-review.json'
PACKAGE_SHA='90b8b3b0970cafa80c076fbf679370144d7b5b9b660668422252d8c4b239800f'

def fixture_render(out,files,code,control,rehearsal):
 """Reuse the ORIGINAL launch wrapper with a schema5 fixture, never the live DB."""
 root=private_dir(out/'launch-wrapper-fixture');release=private_dir(root/'releases'/SOURCE)
 for relative,h in files.items():
  target=release/relative;private_dir(target.parent);atomic(target,(code/relative).read_bytes());require(sha(target)==h,'FIXTURE_SOURCE_COPY_DRIFT')
 data=private_dir(root/'data/hunter')/'hunter.db'
 with closing(sqlite3.connect(Path(rehearsal['verified_schema5_backup']['artifact']['path']).as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(data)) as dst:src.backup(dst)
 data.chmod(0o600);private_dir(root/'jobs/hunter');private_dir(root/'config');private_dir(root/'plans/hunter')
 python=private_dir(root/'venvs/hunter/bin')/'python';atomic(python,(V2/'venvs/hunter/bin/python').read_bytes());python.chmod(0o700)
 env={'DATA_ROOT':str(root/'data'),'HUNTER_API_TOKEN':'fixture-service-credential-A-'+'a'*32,'PROJECTS_INGEST_HUNTER_TOKEN':'fixture-service-credential-B-'+'b'*32,'HUNTER_HOST':'127.0.0.1','HUNTER_PORT':'4011','HUNTER_DB':str(data),'HUNTER_V2_MODE':'1','HUNTER_TENANT_ID':'ikun-main','HUNTER_EXTERNAL_IO_ENABLED':'0','HUNTER_REQUIRE_EXTERNAL_IO_DISABLED':'1','HUNTER_DELIVERY_PROTOCOL':'v2-event','HUNTER_ENGINE':'python'}
 environment=root/'config/hunter.environment.json';atomic(environment,env)
 frozen=root/'config/hunter.accepted.json'
 receipt={'accepted_frozen':True,'worker':'hunter','source_commit':SOURCE,'control_commit':control,'runtime_sha256':files,'argv':[str(python),'-m','hunterradar','run'],'executable_sha256':sha(python),'database_user_version':5,'database_application_id':0x494B0201}
 atomic(frozen,receipt)
 plan={'worker':'hunter','accepted_frozen':True,'candidate_sha':SOURCE,'source_commit':SOURCE,'control_commit':control,'release':str(release),'acceptance_file':str(frozen),'acceptance_sha256':sha(frozen),'environment_file':str(environment),'cwd':str(root/'jobs/hunter'),'argv':receipt['argv'],'runtime_sha256':files}
 _,_,clean=night.validate(plan,root=root);require(clean['HUNTER_EXTERNAL_IO_ENABLED']=='0' and clean['HUNTER_REQUIRE_EXTERNAL_IO_DISABLED']=='1','FIXTURE_HARDOFF_FAILED')
 rendered=night.render(plan,root/'plans/hunter'/SOURCE,root=root);checks=['original_validate_schema5_python_entry','original_render_no_job_install']
 env['HUNTER_EXTERNAL_IO_ENABLED']='1';atomic(environment,env)
 try:night.validate(plan,root=root)
 except ValueError:checks.append('external_enabled_rejected')
 else:raise AssertionError('external_enabled_accepted')
 env['HUNTER_EXTERNAL_IO_ENABLED']='0';atomic(environment,env)
 wrong=copy.deepcopy(receipt);wrong['database_user_version']=4;atomic(frozen,wrong);bad={**plan,'acceptance_sha256':sha(frozen)}
 try:night.validate(bad,root=root)
 except ValueError:checks.append('schema4_receipt_cannot_start_schema5')
 else:raise AssertionError('old_schema_receipt_accepted')
 wrong=copy.deepcopy(receipt);wrong['runtime_sha256'][next(iter(files))]='0'*64;atomic(frozen,wrong);bad={**plan,'acceptance_sha256':sha(frozen),'runtime_sha256':wrong['runtime_sha256']}
 try:night.validate(bad,root=root)
 except ValueError:checks.append('wrong_reader_source_rejected')
 else:raise AssertionError('wrong_reader_accepted')
 atomic(frozen,receipt);require(plan['acceptance_sha256']==sha(frozen),'FIXTURE_NOT_RESTORED');night.validate(plan,root=root)
 return {'checks_passed':checks,'count':len(checks),'original_wrapper_sha256':sha(Path(night.__file__)),'rendered':rendered,'fixture_only':True,'job_installed':False,'process_started':False,'network_connections':0}

def main():
 os.umask(0o077);parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();out=Path(args.output)
 require(out.is_absolute() and not out.exists() and not any(p.is_symlink() for p in out.parents),'NEW_PRIVATE_OUTPUT_REQUIRED');private_dir(out)
 for path,h in ((PROJECTS,PROJECTS_SHA),(INTAKE,INTAKE_SHA),(REHEARSAL,REHEARSAL_SHA),(PACKAGE,PACKAGE_SHA)):require(sha(path)==h,'PINNED_INPUT_DRIFT')
 projects=read_json(PROJECTS);intake=read_json(INTAKE);rehearsal=read_json(REHEARSAL);validate_artifacts(projects);validate_artifacts(rehearsal)
 code=Path(intake['staged_code_root']);files=intake['staged_git_sha256']
 for p,h in files.items():require(sha(code/p)==h,'STAGED_F9_CODE_DRIFT')
 control=subprocess.check_output(['git','rev-parse','8ab1faa'],cwd=ROOT,text=True).strip()
 system=System(None);legacy=read_json(LEGACY_PLAN);projection={key:copy.deepcopy(legacy[key]) for key in ('protected_processes','protected_files_sha256','v2_database_identities')}
 projection['protected_processes']['v2_web']=projects['web_window']['new_process']
 protected=guard(system,projection)
 for process in projects['web_window']['new_tree']:require(same_process(system.process(process['pid']),process),'ACCEPTED_WEB_CHILD_DRIFT')
 socket=WebOps(None).socket_proof(system.tree(projects['web_window']['new_process']['pid']));require(socket==projects['web_window']['new_socket'],'ACCEPTED_WEB_SOCKET_DRIFT')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));health={}
 for name,port,flag in (('web',4000,None),('hunter',4011,'external_io_enabled'),('tracking',4012,'external_collection_enabled')):
  with opener.open('http://127.0.0.1:'+str(port)+'/health/ready',timeout=4) as response:
   require(response.status==200,'CURRENT_SERVICE_NOT_READY');data=json.load(response)['data'];health[name]={'status':200}
   if flag:require(data.get(flag) is False,'CURRENT_EXTERNAL_IO_ENABLED');health[name][flag]=False
 current_env=V2/'config/hunter.environment.json';info=current_env.lstat();require(info.st_mode&0o777==0o600 and info.st_nlink==1,'HUNTER_ENV_NOT_PRIVATE');env=read_json(current_env)
 require(env['HUNTER_EXTERNAL_IO_ENABLED']=='0' and env['HUNTER_REQUIRE_EXTERNAL_IO_DISABLED']=='1' and env['HUNTER_DB']==str(V2/'data/hunter/hunter.db'),'ORIGINAL_HUNTER_MODE_CHANGED')
 python=V2/'venvs/hunter/bin/python';acceptance=V2/'config'/('hunter.accepted.'+SOURCE+'.json');release=V2/'releases'/SOURCE
 frozen={'accepted_frozen':True,'worker':'hunter','source_commit':SOURCE,'control_commit':control,'runtime_sha256':files,'argv':[str(python),'-m','hunterradar','run'],'executable_sha256':sha(python),'database_user_version':5,'database_application_id':0x494B0201}
 frozen_bytes=(json.dumps(frozen,indent=2)+'\n').encode()
 future={'worker':'hunter','accepted_frozen':True,'candidate_sha':SOURCE,'source_commit':SOURCE,'control_commit':control,'release':str(release),'acceptance_file':str(acceptance),'acceptance_sha256':hashlib.sha256(frozen_bytes).hexdigest(),'environment_file':str(current_env),'cwd':str(V2/'jobs/hunter'),'argv':frozen['argv'],'runtime_sha256':files,'previous_worker_release':'75b81a2b5210e41bdf8522467c7fba2a6a6e693c'}
 atomic(out/'future-acceptance.json',frozen_bytes);atomic(out/'future-worker-plan.json',future)
 during=copy.deepcopy(projection);during['protected_processes'].pop('v2_Hunter');during['protected_files_sha256'].pop(str(Path.home()/'Library/LaunchAgents/ca.ikun.v2.c0lite.hunter.plist'))
 atomic(out/'current-protection-projection.json',projection);atomic(out/'during-hunter-maintenance-protection.json',during)
 fixture=fixture_render(out,files,code,control,rehearsal)
 report={'state':'PREPARED_HUNTER_F9_READER_AND_CURRENT_GUARDS_NOT_EXECUTED','prepared_at':utc(),'source_commit':SOURCE,'control_commit':control,'source_intake':artifact(INTAKE),'projects_actual_receipt':artifact(PROJECTS),'clone_rehearsal':artifact(REHEARSAL),'formal_directory_package':artifact(PACKAGE),'source_code_root':str(code),'runtime_git_files':len(files),'future_release':str(release),'future_python_argv':frozen['argv'],'future_plan':artifact(out/'future-worker-plan.json'),'future_acceptance':artifact(out/'future-acceptance.json'),'legacy_protection_plan_preserved':{'path':str(LEGACY_PLAN),'sha256':sha(LEGACY_PLAN)},'current_protection':artifact(out/'current-protection-projection.json'),'during_hunter_protection':artifact(out/'during-hunter-maintenance-protection.json'),'current_web_tree_checked':projects['web_window']['new_tree'],'current_socket_checked':socket,'protected_before':protected,'health_before':health,'hunter_environment_sha256':sha(current_env),'reader_schema_version':5,'old_reader_forbidden_after_migration':True,'fixture_original_wrapper_checks':fixture,'tool_source_sha256':sha(__file__),'runtime_database_connections':0,'runtime_database_writes':0,'runtime_files_created':0,'service_mutations':0,'new_provider_calls':0,'Watch_writes':0,'next_builds':0,'execution_entry_in_this_tool':False,'remaining_gate':'root must review concrete native maintenance executor/argv before stop, sole005 migration, directory apply and reader cutover'}
 atomic(out/'PREPARATION-ONLY.json',report);print(json.dumps({'state':report['state'],'receipt':str(out/'PREPARATION-ONLY.json'),'sha256':sha(out/'PREPARATION-ONLY.json'),'wrapper_fixture_checks':fixture['count'],'runtime_mutations':0},ensure_ascii=False))

if __name__=='__main__':main()
