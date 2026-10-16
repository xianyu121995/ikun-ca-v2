#!/usr/bin/env python3
"""Synthetic native operations and fresh private SQLite fixtures, never runtime services."""
from contextlib import ExitStack,redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

import hunter_directory_maintenance as m
from takeover_operator import Journal as RealJournal,EXECUTION,MANAGER,OWNER,JOB_SPECS,MANUAL


def identity(pid=2608,parent=1):
 return {'pid':pid,'ppid':parent,'uid':os.getuid(),'started_utc':'2026-10-15T18:50:24+00:00','executable':'fixture-python','cwd':str(m.V2/'jobs/hunter')}


def receipt(count=88):
 return {'protocol':'hunter-takeover-package-v2','execution_id':EXECUTION,'package_sha256':m.PACKAGE_SHA,'kind':'directory','duplicate_package':False,'new_business_rows':count,'new_private_facts':6575,'new_private_receipts':6575,'network_requests':0,'watch_writes':0,'notifications':0,'commands':0,'public_events':0,'inserted':{'hunters':count,'private_facts':6575,'private_receipts':6575,'hunter_takeover_baselines':71}}


def replay(original):
 return {**copy.deepcopy(original),'duplicate_package':True,'original_result':copy.deepcopy(original),'new_business_rows':0,'new_private_facts':0,'new_private_receipts':0,'inserted':{}}


class FakeOps:
 def __init__(self,*_,loaded=True):
  self.loaded=loaded;self.pid=2608;self.alive={2608:identity()} if loaded else {};self.actions=[];self.on_stop=None;self.bootstrap_unknown=False
 def process(self,pid):return copy.deepcopy(self.alive.get(pid))
 def job(self):return {'loaded':self.loaded,'pid':self.pid if self.loaded else None}
 def tree(self,pid):return [copy.deepcopy(p) for p in self.alive.values() if p['pid']==pid or p['ppid']==pid]
 def bootout(self):
  self.actions.append(('bootout',m.LABEL));self.loaded=False;self.alive={}
  if self.on_stop:self.on_stop()
 def fence(self):m.require(not self.loaded,'FIXTURE_HUNTER_LOADED')
 def bootstrap(self):
  reader='f9' if plistlib.loads(m.PLIST.read_bytes())==m.expected_job() else 'legacy4';self.actions.append(('bootstrap',reader))
  if self.bootstrap_unknown:raise m.SafeFailure('SIMULATED_BOOTSTRAP_UNKNOWN')
  self.pid+=1000;self.loaded=True;self.alive={self.pid:identity(self.pid)}
 def ready(self,*_):m.require(self.loaded,'FIXTURE_NOT_READY')


class Fixture(unittest.TestCase):
 def setUp(self):
  self.mask=os.umask(0o077);self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='ik-hunter-maint-');self.root=Path(self.tmp.name);self.root.chmod(0o700);self.stack=ExitStack();self.native=m.private_dir(self.root/'native');self.out=m.private_dir(self.root/'output');self.code=m.private_dir(self.root/'code');self.databases={}
  for name,appid,version in (('hunter',0x494B0201,4),('auth',0x494B0204,2),('projects',0x494B0203,2),('tracking',0x494B0202,4)):
   path=m.private_dir(self.native/'data'/name)/(name+'.db')
   with sqlite3.connect(path) as db:
    db.executescript('PRAGMA application_id='+str(appid)+';PRAGMA user_version='+str(version)+';CREATE TABLE hunters(id TEXT PRIMARY KEY,notes TEXT,revision INTEGER,enabled INTEGER,profile_status TEXT,user_id TEXT,followers INTEGER,mode TEXT,baseline_ready INTEGER,watch_covered INTEGER);CREATE TABLE state(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE worker_lease(id PRIMARY KEY,expires_at);CREATE TABLE discoveries(id TEXT);CREATE TABLE task_outbox(id TEXT);CREATE TABLE _schema_migrations(version PRIMARY KEY);CREATE TABLE _migration_checksums(version PRIMARY KEY);INSERT INTO hunters VALUES("manual","keep human notes",7,0,"pending",NULL,NULL,NULL,0,0);INSERT INTO state VALUES("cursor_secret","fixture-not-a-credential");INSERT INTO state VALUES("retention_clock_highwater","0");INSERT INTO worker_lease VALUES(1,0);INSERT INTO _schema_migrations VALUES(4);INSERT INTO _migration_checksums VALUES(4);')
   path.chmod(0o600);self.databases[name]=path
  self.plist=m.private_dir(self.native/'agents')/(m.LABEL+'.plist');m.atomic(self.plist,plistlib.dumps({'legacy4':True}))
  self.plan_dir=self.native/'plans/hunter'/m.SOURCE;self.release=self.native/'releases'/m.SOURCE;self.acceptance=m.private_dir(self.native/'config')/'hunter.accepted.json';m.private_dir(self.native/'jobs/hunter')
  self.rehearsal=m.private_dir(self.root/'rehearsal')/'REHEARSAL_ONLY.json';m.atomic(self.rehearsal.parent/'before.private.json',m.fingerprint(self.databases['hunter']))
  self.package=self.root/'package.json';m.atomic(self.package,{'source_sha256':'fixture-source','ownership_sha256':'fixture-ownership'})
  self.journal=self.root/'journal.json';m.atomic(self.journal,{'execution_id':EXECUTION,'owner_thread':MANAGER,'operator_thread':OWNER,'root_operates_stop':False,'stop_jobs':list(JOB_SPECS),'approved_manual_stop':MANUAL,'migrated_domains':['projects'],'state':'legacy_snapshots_ready_waiting_owner_imports','operator_steps':{'preserve':'original stop'}})
  for name,value in {'V2':self.native,'OUTPUT':self.out,'DATABASE':self.databases['hunter'],'DATABASES':self.databases,'PLIST':self.plist,'PLAN_DIR':self.plan_dir,'RELEASE':self.release,'ACCEPTANCE':self.acceptance,'REHEARSAL':self.rehearsal,'PACKAGE':self.package,'JOURNAL':self.journal}.items():self.stack.enter_context(patch.object(m,name,value))
 def tearDown(self):self.stack.close();self.tmp.cleanup();os.umask(self.mask)
 def install(self,plan):
  m.private_dir(self.plan_dir);m.atomic(self.plan_dir/(m.LABEL+'.plist'),plistlib.dumps(m.expected_job()));m.atomic(self.plan_dir/'worker.json',{'fixture_f9':True})
 def checkpoint(self):return m.sqlite_backup(self.databases['hunter'],m.private_dir(self.out/('cp-'+uuid.uuid4().hex)),strict_foreign_keys=True)
 def set_version(self,version):
  with sqlite3.connect(self.databases['hunter']) as db:db.execute('PRAGMA user_version='+str(version))
 def window(self):
  original=m.copy_private(self.plist,self.out/'original.plist');return {'stopped':True,'tree':[identity()],'original_plist':original}
 def plan(self):return {'initial_plist_sha256':m.sha(self.plist),'current_reader':'legacy4'}


class Recovery(Fixture):
 def setUp(self):super().setUp();self.ops=FakeOps(loaded=False);self.window_data=self.window();self.state={};self.plan_data=self.plan();self.stack.enter_context(patch.object(m,'install_reader_plan',side_effect=self.install))
 def restore(self,version,checkpoint=None):m.compatible_restore(self.state,self.window_data,lambda:None,self.ops,self.plan_data,version,checkpoint=checkpoint)
 def test_schema4_uses_old_reader_only_before_any_schema5_observation(self):
  self.restore(4);self.assertEqual(self.ops.actions,[('bootstrap','legacy4')]);self.assertEqual(self.window_data['reader'],'legacy4')
 def test_schema5_never_uses_old_plist(self):
  self.set_version(5);self.restore(5,self.checkpoint());self.assertEqual(self.ops.actions,[('bootstrap','f9')]);self.assertTrue(self.state['schema5_observed'])
 def test_sticky_schema5_refuses_downgraded_metadata_without_bootstrap(self):
  self.state['schema5_observed']=True
  with self.assertRaisesRegex(m.SafeFailure,'STICKY_DOWNGRADE'):self.restore(4)
  self.assertEqual(self.ops.actions,[])
 def test_schema5_missing_checkpoint_cannot_bootstrap(self):
  self.set_version(5)
  with self.assertRaisesRegex(m.SafeFailure,'CHECKPOINT_REQUIRED'):self.restore(5)
  self.assertEqual(self.ops.actions,[])
 def test_schema5_stale_checkpoint_cannot_bootstrap(self):
  self.set_version(5);cp=self.checkpoint()
  with sqlite3.connect(self.databases['hunter']) as db:db.execute('UPDATE hunters SET notes="new human edit"')
  with self.assertRaisesRegex(m.SafeFailure,'CHECKPOINT_NOT_CURRENT'):self.restore(5,cp)
  self.assertEqual(self.ops.actions,[])
 def test_missing_f9_plan_never_falls_back_to_schema4_binary(self):
  self.set_version(5)
  with patch.object(m,'install_reader_plan',side_effect=m.SafeFailure('F9_PLAN_MISSING')):
   with self.assertRaisesRegex(m.SafeFailure,'F9_PLAN_MISSING'):self.restore(5,self.checkpoint())
  self.assertEqual(self.ops.actions,[]);self.assertTrue(self.state['schema5_observed'])
 def test_reparented_original_cannot_be_declared_absent(self):
  self.ops.alive[2608]=identity(2608,77)
  with self.assertRaisesRegex(m.SafeFailure,'TREE_STILL_ALIVE'):self.restore(4)
  self.assertEqual(self.ops.actions,[])
 def test_unknown_bootstrap_unloaded_not_reissued(self):
  self.set_version(5);self.ops.bootstrap_unknown=True;cp=self.checkpoint()
  with self.assertRaisesRegex(m.SafeFailure,'SIMULATED_BOOTSTRAP_UNKNOWN'):self.restore(5,cp)
  with self.assertRaisesRegex(m.SafeFailure,'BOOTSTRAP_UNKNOWN_NO_RETRY'):self.restore(5,cp)
  self.assertEqual(self.ops.actions,[('bootstrap','f9')])
 def test_unknown_bootstrap_loaded_is_verified_without_second_bootstrap(self):
  self.set_version(5);cp=self.checkpoint();self.restore(5,cp);self.window_data.pop('restored');self.restore(5,cp);self.assertEqual(self.ops.actions,[('bootstrap','f9')])
 def test_unexpected_plist_is_preserved_not_overwritten(self):
  self.set_version(5);m.atomic(self.plist,b'foreign edit')
  with self.assertRaisesRegex(m.SafeFailure,'PLIST_UNEXPECTED_CHANGE'):self.restore(5,self.checkpoint())
  self.assertEqual(self.plist.read_bytes(),b'foreign edit');self.assertEqual(self.ops.actions,[])
 def test_prearmed_f9_plist_can_return_to_legacy_only_if_005_not_committed(self):
  m.prearm_f9_plist(self.window_data,lambda:None,self.ops,self.plan_data);self.assertEqual(plistlib.loads(self.plist.read_bytes()),m.expected_job());self.assertEqual(self.ops.actions,[])
  self.restore(4);self.assertEqual(self.ops.actions,[('bootstrap','legacy4')])


class StorageAndReceipts(Fixture):
 def test_prepare_never_overwrites_a_dangling_plan_alias(self):
  path=self.out/'execution-plan.json';path.symlink_to(self.root/'foreign-missing')
  with self.assertRaisesRegex(m.SafeFailure,'NEW_HUNTER_PLAN_REQUIRED'):m.prepare(path)
  self.assertTrue(path.is_symlink())
 def test_original_87_cannot_be_washed_into_pass_by_zero_replay(self):
  with self.assertRaisesRegex(m.SafeFailure,'COUNTS_MISMATCH'):m.verify_apply(receipt(87))
  with self.assertRaisesRegex(m.SafeFailure,'CANNOT_WASH'):m.verify_apply(replay(receipt(87)))
 def test_replay_missing_original_or_wrong_scope_rejected(self):
  bad=replay(receipt());bad.pop('original_result')
  with self.assertRaises(m.SafeFailure):m.verify_apply(bad)
  bad=replay(receipt());bad['original_result']['kind']='supplement'
  with self.assertRaises(m.SafeFailure):m.verify_apply(bad)
 def test_original_side_effects_and_boolean_counts_rejected(self):
  bad=replay(receipt());bad['original_result']['notifications']=1
  with self.assertRaises(m.SafeFailure):m.verify_apply(bad)
  bad=receipt();bad['network_requests']=False
  with self.assertRaises(m.SafeFailure):m.verify_apply(bad)
 def test_persisted_source_binding_checked_separately_from_zero_counters(self):
  result=receipt();m.verify_apply(replay(result))
  with sqlite3.connect(self.databases['hunter']) as db:
   db.execute('CREATE TABLE hunter_takeover_runs(package_sha256,source_sha256,ownership_sha256,projects_sha256,report_json)');db.execute('INSERT INTO hunter_takeover_runs VALUES(?,?,?,?,?)',(m.PACKAGE_SHA,'different-source','fixture-ownership','not-applicable:directory-v2',json.dumps(result)))
  with self.assertRaisesRegex(m.SafeFailure,'SOURCE_BINDING_MISMATCH'):m.verify_persisted_run(self.databases['hunter'],replay(result))
 def test_changed_stopped_seed_requires_new_rehearsal(self):
  m.require_rehearsed_seed(self.databases['hunter'])
  with sqlite3.connect(self.databases['hunter']) as db:db.execute('UPDATE hunters SET notes="new edit",revision=8')
  with self.assertRaisesRegex(m.SafeFailure,'REHEARSAL_REQUIRED'):m.require_rehearsed_seed(self.databases['hunter'])
 def new_seed_plan(self):
  directory=m.private_dir(self.root/'current-rehearsal');proof=directory/'REHEARSAL_ONLY.json';m.atomic(proof,{'fixture':True});m.atomic(directory/'before.private.json',m.fingerprint(self.databases['hunter']))
  return {'current_seed_rehearsal':m.artifact(proof)}
 def test_plan_bound_current_seed_keeps_old_seed_intact(self):
  with sqlite3.connect(self.databases['hunter']) as db:db.execute('UPDATE hunters SET notes="current human text",revision=8')
  plan=self.new_seed_plan();m.require_rehearsed_seed(self.databases['hunter'],plan)
  with self.assertRaisesRegex(m.SafeFailure,'REHEARSAL_REQUIRED'):m.require_rehearsed_seed(self.databases['hunter'])
 def test_plan_bound_rehearsal_tamper_fails_before_seed_read(self):
  plan=self.new_seed_plan();m.atomic(plan['current_seed_rehearsal']['path'],{'fixture':'changed'})
  with self.assertRaisesRegex(m.SafeFailure,'CURRENT_REHEARSAL_HASH_MISMATCH'):m.require_rehearsed_seed(self.databases['hunter'],plan)
 def test_plan_bound_seed_still_rejects_later_manual_changes(self):
  plan=self.new_seed_plan()
  with sqlite3.connect(self.databases['hunter']) as db:db.execute('UPDATE hunters SET notes="latest preserved text",revision=9')
  with self.assertRaisesRegex(m.SafeFailure,'REHEARSAL_REQUIRED'):m.require_rehearsed_seed(self.databases['hunter'],plan)
 def test_live_lease_is_never_deleted_to_make_migration_pass(self):
  with sqlite3.connect(self.databases['hunter']) as db:db.execute('UPDATE worker_lease SET expires_at=9999999999')
  with self.assertRaisesRegex(m.SafeFailure,'NO_DELETE'):m.wait_lease(FakeOps(loaded=False),timeout=0)
  with sqlite3.connect(self.databases['hunter']) as db:self.assertEqual(db.execute('SELECT expires_at FROM worker_lease').fetchone()[0],9999999999)
 def test_new_runtime_release_is_not_allowed_to_contain_unlisted_imports(self):
  p=self.code/'services/hunter-worker/python/hunterradar/__init__.py';m.private_dir(p.parent);m.atomic(p,b'# fixture code\n');a=self.out/'acceptance.json';m.atomic(a,{'fixture':True});plan={'runtime_files':{str(p.relative_to(self.code)):m.sha(p)},'code_root':str(self.code),'acceptance':m.artifact(a)}
  m.stage_reader(plan);extra=self.release/'services/hunter-worker/python/sitecustomize.py';m.atomic(extra,b'# unexpected import hook\n')
  with self.assertRaisesRegex(m.SafeFailure,'INVENTORY_DRIFT'):m.stage_reader(plan)
  self.assertTrue(extra.exists())
 def test_release_symlink_and_bad_f9_bytes_refused(self):
  m.private_dir(self.release.parent);self.release.symlink_to(self.root/'foreign')
  with self.assertRaisesRegex(m.SafeFailure,'RELEASE_ALIAS'):m.stage_reader({})
  self.assertTrue(self.release.is_symlink());self.release.unlink()
  p=self.code/'services/hunter-worker/python/hunterradar/__init__.py';m.private_dir(p.parent);m.atomic(p,b'altered')
  with self.assertRaisesRegex(m.SafeFailure,'COPY_DRIFT'):m.stage_reader({'runtime_files':{str(p.relative_to(self.code)):'0'*64},'code_root':str(self.code)})
  self.assertFalse(self.release.exists())


class FullFlow(Fixture):
 def setUp(self):
  super().setUp();self.ops=FakeOps();self.plan_data={**self.plan(),'tool_source_sha256':m.sha(m.__file__),'initial_hunter':self.ops.process(2608),'initial_tree':self.ops.tree(2608),'during_protection':{'protected_processes':{'web':identity(54011),'tracking':identity(25225)}},'web_tree':[identity(54011),identity(54012,54011)]};self.plan_path=self.root/'plan.json';m.atomic(self.plan_path,self.plan_data)
  self.apply_calls=0;self.migrate_calls=0;self.migration_fault=None;self.apply_fault=None;self.import_count=88
  self.stack.enter_context(patch.object(m,'HunterOps',return_value=self.ops));self.stack.enter_context(patch.object(m,'Journal',side_effect=lambda:RealJournal(self.journal)));self.stack.enter_context(patch.object(m,'immutable'));self.stack.enter_context(patch.object(m,'peers',return_value={'protected':True}));self.stack.enter_context(patch.object(m,'stage_reader'));self.stack.enter_context(patch.object(m,'install_reader_plan',side_effect=self.install));self.stack.enter_context(patch.object(m,'owner',side_effect=self.owner));self.stack.enter_context(patch.object(m.subprocess,'check_output',side_effect=self.git));self.stack.enter_context(redirect_stdout(io.StringIO()))
 def git(self,args,**_):
  values={('git','rev-parse','HEAD'):'fixture-candidate\n',('git','branch','--show-current'):'codex/integration\n',('git','status','--porcelain'):'',('git','rev-parse','main'):'63e8a2857241c6a76226f21435e40db9736a1e7e\n'};return values[tuple(args)]
 def owner(self,plan,ops,name,args):
  self.assertFalse(ops.loaded);dbpath=self.databases['hunter']
  if name=='inspect':
   with sqlite3.connect(dbpath) as db:result={'schema':db.execute('PRAGMA user_version').fetchone()[0]}
  elif name=='migrate':
   self.migrate_calls+=1
   self.assertEqual(plistlib.loads(self.plist.read_bytes()),m.expected_job(),'future reboot must point only to F9 before005')
   if self.migration_fault=='before_commit':raise m.SafeFailure('SIMULATED_MIGRATION_ROLLBACK')
   with sqlite3.connect(dbpath) as db:db.executescript('PRAGMA user_version=5;CREATE TABLE hunter_takeover_runs(package_sha256 PRIMARY KEY,source_sha256,ownership_sha256,projects_sha256,report_json);INSERT INTO _schema_migrations VALUES(5);INSERT INTO _migration_checksums VALUES(5);')
   if self.migration_fault=='after_commit':raise m.SafeFailure('SIMULATED_MIGRATION_UNKNOWN_AFTER_COMMIT')
   result={'migrated':5}
  else:
   self.apply_calls+=1
   with sqlite3.connect(dbpath) as db:
    previous=db.execute('SELECT report_json FROM hunter_takeover_runs WHERE package_sha256=?',(m.PACKAGE_SHA,)).fetchone()
    if previous:result=replay(json.loads(previous[0]))
    else:
     result=receipt(self.import_count);db.executemany('INSERT INTO hunters VALUES(?,?,1,0,"pending",NULL,NULL,NULL,0,0)',[(str(i),'synthetic directory')for i in range(self.import_count)]);db.execute('INSERT INTO state VALUES(?,?)',(m.PREFIX+'fact:synthetic','{}'));db.execute('UPDATE state SET value="1234" WHERE key="retention_clock_highwater"');db.execute('INSERT INTO hunter_takeover_runs VALUES(?,?,?,?,?)',(m.PACKAGE_SHA,'fixture-source','fixture-ownership','not-applicable:directory-v2',json.dumps(result)))
   if self.apply_fault=='after_commit' and not previous:raise m.SafeFailure('SIMULATED_APPLY_UNKNOWN_AFTER_COMMIT')
  out=self.out/(name+'-'+uuid.uuid4().hex+'.json');m.atomic(out,result);return out,result
 def execute(self,**kwargs):m.execute('fixture-candidate',self.plan_path,m.sha(self.plan_path),**kwargs)
 def rebase(self):
  self.plan_data['initial_hunter']=self.ops.process(self.ops.pid);self.plan_data['initial_tree']=self.ops.tree(self.ops.pid);self.plan_data['initial_plist_sha256']=m.sha(self.plist);self.plan_data['current_reader']='f9' if plistlib.loads(self.plist.read_bytes())==m.expected_job() else 'legacy4';m.atomic(self.plan_path,self.plan_data)
 def test_success_four_library_backups_and_f9_only_restart(self):
  self.execute();d=m.read_json(self.journal);self.assertEqual(d['migrated_domains'],['projects','hunter']);self.assertEqual(d['operator_steps'],{'preserve':'original stop'});self.assertEqual(d['state'],'legacy_snapshots_ready_waiting_owner_imports');self.assertEqual(self.ops.actions,[('bootout',m.LABEL),('bootstrap','f9')])
  final=m.read_json(self.out/'final-receipt.json');self.assertEqual(sum(len(final[k])for k in ('before_online','stopped','after_import')),12);self.assertTrue(final['schema5_sticky']);self.assertEqual(final['schema_version'],5);self.assertEqual(self.migrate_calls,1)
 def test_repeat_complete_checks_artifacts_and_does_no_service_action(self):
  self.execute();calls=self.apply_calls;self.execute();self.assertEqual(self.apply_calls,calls);self.assertEqual(self.ops.actions,[('bootout',m.LABEL),('bootstrap','f9')])
 def test_schema4_failure_restores_old_only_before_005_commit(self):
  self.migration_fault='before_commit'
  with self.assertRaises(SystemExit):self.execute()
  self.assertEqual(self.ops.actions,[('bootout',m.LABEL),('bootstrap','legacy4')]);self.assertEqual(m.read_json(self.journal)['migrated_domains'],['projects'])
 def test_unknown_005_commit_restores_only_f9_and_keeps_sticky5(self):
  self.migration_fault='after_commit'
  with self.assertRaises(SystemExit):self.execute()
  self.assertEqual(self.ops.actions,[('bootout',m.LABEL),('bootstrap','f9')]);s=m.read_json(self.journal)['maintenance_steps'][m.PHASE];self.assertTrue(s['schema5_observed']);self.assertEqual(s['last_failure']['recovery'],'f9_schema5_reader_restored')
 def test_unknown_apply_commit_resumes_same_package_without_new_directory(self):
  self.apply_fault='after_commit'
  with self.assertRaises(SystemExit):self.execute()
  self.assertEqual(self.ops.actions,[('bootout',m.LABEL),('bootstrap','f9')]);self.rebase()
  with self.assertRaisesRegex(m.SafeFailure,'NEW_REVIEWED_HUNTER_PLAN'):self.execute()
  self.execute(resume_recovered=True);self.assertEqual(self.migrate_calls,1)
  with sqlite3.connect(self.databases['hunter']) as db:self.assertEqual(db.execute('SELECT count(*) FROM hunters').fetchone()[0],89)
  self.assertEqual(self.ops.actions,[('bootout',m.LABEL),('bootstrap','f9'),('bootout',m.LABEL),('bootstrap','f9')])
 def test_stopped_seed_race_restores_schema4_and_preserves_human_edit(self):
  def edit():
   with sqlite3.connect(self.databases['hunter']) as db:db.execute('UPDATE hunters SET notes="legal new edit",revision=8 WHERE id="manual"')
  self.ops.on_stop=edit
  with self.assertRaises(SystemExit):self.execute()
  self.assertEqual(self.migrate_calls,0);self.assertEqual(self.apply_calls,0);self.assertEqual(self.ops.actions,[('bootout',m.LABEL),('bootstrap','legacy4')])
  with sqlite3.connect(self.databases['hunter']) as db:self.assertEqual(db.execute('SELECT notes,revision FROM hunters WHERE id="manual"').fetchone(),('legal new edit',8))
 def test_bad_first_count_cannot_become_success_after_recovery_zero_replay(self):
  self.import_count=87
  with self.assertRaises(SystemExit):self.execute()
  self.rebase()
  with self.assertRaises(SystemExit):self.execute(resume_recovered=True)
  d=m.read_json(self.journal);self.assertEqual(d['migrated_domains'],['projects']);self.assertIn('CANNOT_WASH',d['maintenance_steps'][m.PHASE]['last_failure']['reason']);self.assertNotIn(('bootstrap','legacy4'),self.ops.actions)
 def test_all_new_web_children_are_protected_from_stop_subtree(self):
  real=m.stop_owned_job_once
  def check(state,save,ops,expected,protected,**kwargs):
   self.assertTrue({54011,54012,25225}<=set(protected));return real(state,save,ops,expected,protected,**kwargs)
  with patch.object(m,'stop_owned_job_once',side_effect=check):self.execute()
 def test_readonly_status_does_not_write_journal_or_open_runtime_database(self):
  before=m.sha(self.journal);r=m.readonly_status(self.plan_path,m.sha(self.plan_path));self.assertEqual(r['state'],'not_started');self.assertEqual(r['runtime_database_connections'],0);self.assertEqual(m.sha(self.journal),before);self.assertEqual(self.ops.actions,[])


if __name__=='__main__':unittest.main()
