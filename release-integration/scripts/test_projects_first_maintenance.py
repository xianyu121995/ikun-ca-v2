#!/usr/bin/env python3
"""Synthetic process/launchd tests; SQLite writes only in new /private/tmp fixtures."""
import copy
from contextlib import ExitStack,redirect_stdout
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import projects_first_maintenance as m
from takeover_operator import Journal as RealJournal,EXECUTION,MANAGER,OWNER,JOB_SPECS,MANUAL


def process(pid=101,ppid=1):
 return {'pid':pid,'ppid':ppid,'uid':os.getuid(),'started_utc':'2026-10-16T07:27:09+00:00','executable':'fixture-node','cwd':str(m.V2/'releases'/m.BASE)}


class FakeWeb:
 def __init__(self,*_):
  self.loaded=True;self.pid=101;self.alive={101:process(),102:process(102,101)};self.actions=[];self.extra=[];self.socket_path=None;self.socket_bad=False;self.bootstrap_unknown=False
 def process(self,pid):return copy.deepcopy(self.alive.get(pid))
 def tree(self,pid):return [copy.deepcopy(p) for p in self.alive.values() if p['pid']==pid or p['ppid']==pid]+copy.deepcopy(self.extra)
 def job(self):return {'loaded':self.loaded,'pid':self.pid if self.loaded else None}
 def bootout(self):self.actions.append('bootout');self.loaded=False;self.alive={}
 def bootstrap(self):
  self.actions.append('bootstrap')
  if self.bootstrap_unknown:raise m.SafeFailure('BOOTSTRAP_OUTCOME_UNKNOWN')
  self.loaded=True;self.pid+=1000;self.alive={self.pid:process(self.pid),self.pid+1:process(self.pid+1,self.pid)}
 def ready(self,_=30):
  if not self.loaded:raise m.SafeFailure('NOT_READY')
 def fence(self):m.require(not self.loaded,'FIXTURE_WEB_STILL_RUNNING')
 def socket_proof(self,tree):
  m.require(not self.socket_bad,'SOCKET_PROOF_FAILED');return {'path':'/private/tmp/fixture/p.sock','holder_pids':[tree[-1]['pid']],'mode':'0600'}


class Lifecycle(unittest.TestCase):
 def setUp(self):self.ops=FakeWeb();self.expected=self.ops.process(101);self.state={};self.saves=[]
 def save(self):self.saves.append(copy.deepcopy(self.state))
 def stop(self,**kwargs):m.stop_web_once(self.state,self.save,self.ops,self.expected,[2608,25225,39523],**kwargs)
 def test_stop_and_reconcile_only_one_bootout(self):
  self.stop();self.stop();self.assertEqual(self.ops.actions,['bootout']);self.assertTrue(self.state['stopped'])
 def test_pid_reuse_blocks_before_any_action(self):
  self.ops.alive[101]['started_utc']='reused'
  with self.assertRaisesRegex(m.SafeFailure,'IDENTITY_DRIFT'):self.stop()
  self.assertEqual(self.ops.actions,[])
 def test_cwd_drift_blocks_before_any_action(self):
  self.ops.alive[101]['cwd']='/unrelated'
  with self.assertRaises(m.SafeFailure):self.stop()
  self.assertEqual(self.ops.actions,[])
 def test_reviewed_child_replacement_requires_new_plan(self):
  child=self.ops.process(102);self.ops.alive[102]['started_utc']='new-child'
  with self.assertRaisesRegex(m.SafeFailure,'CHILD_IDENTITY_DRIFT'):self.stop(expected_tree=[self.expected,child])
  self.assertEqual(self.ops.actions,[])
 def test_protected_descendant_never_stopped(self):
  self.ops.extra=[process(2608,101)]
  with self.assertRaisesRegex(m.SafeFailure,'PROTECTED_PROCESS'):self.stop()
  self.assertEqual(self.ops.actions,[])
 def test_late_protected_descendant_blocks_bootout(self):
  def save():self.save();self.ops.extra=[process(25225,101)]
  with self.assertRaisesRegex(m.SafeFailure,'PROTECTED_PROCESS'):m.stop_web_once(self.state,save,self.ops,self.expected,[25225])
  self.assertEqual(self.ops.actions,[])
 def test_unknown_loaded_stop_is_not_reissued(self):
  self.state.update(stop_intent='earlier',tree=[self.expected])
  with self.assertRaisesRegex(m.SafeFailure,'NO_AUTOMATIC_RETRY'):self.stop()
  self.assertEqual(self.ops.actions,[])
 def test_unknown_unloaded_stop_reconciles_without_action(self):
  self.state.update(stop_intent='earlier',tree=[self.expected]);self.ops.loaded=False;self.ops.alive={};self.stop()
  self.assertTrue(self.state['stopped']);self.assertEqual(self.ops.actions,[])
 def test_reparented_child_is_still_alive_no_force_kill(self):
  self.state.update(stop_intent='earlier',tree=[self.ops.process(102)]);self.ops.loaded=False;self.ops.alive.pop(101);self.ops.alive[102]['ppid']=1
  with self.assertRaisesRegex(m.SafeFailure,'NO_FORCE_KILL'):self.stop(timeout=0)
  self.assertEqual(self.ops.actions,[])
 def test_recorded_stop_does_not_accept_reappeared_original(self):
  self.state.update(stopped=True,tree=[self.expected]);self.ops.loaded=False
  with self.assertRaisesRegex(m.SafeFailure,'REAPPEARED'):self.stop()
 def test_restore_and_repeat_use_one_bootstrap(self):
  self.stop();m.restore_web_once(self.state,self.save,self.ops);m.restore_web_once(self.state,self.save,self.ops)
  self.assertEqual(self.ops.actions,['bootout','bootstrap']);self.assertTrue(self.state['restored']);self.assertIn('new_socket',self.state)
 def test_unknown_bootstrap_with_unloaded_job_is_not_reissued(self):
  self.ops.loaded=False;self.state['restore_intent']='earlier'
  with self.assertRaisesRegex(m.SafeFailure,'NO_AUTOMATIC_RETRY'):m.restore_web_once(self.state,self.save,self.ops)
  self.assertEqual(self.ops.actions,[])
 def test_unknown_bootstrap_loaded_can_be_verified_without_action(self):
  self.state['restore_intent']='earlier';m.restore_web_once(self.state,self.save,self.ops);self.assertEqual(self.ops.actions,[])
 def test_wrong_release_never_claims_restored(self):
  self.ops.alive[101]['cwd']='/different/release'
  with self.assertRaisesRegex(m.SafeFailure,'IDENTITY_MISMATCH'):m.restore_web_once(self.state,self.save,self.ops)
  self.assertNotIn('restored',self.state)
 def test_socket_failure_never_claims_restored(self):
  self.ops.socket_bad=True
  with self.assertRaisesRegex(m.SafeFailure,'SOCKET_PROOF_FAILED'):m.restore_web_once(self.state,self.save,self.ops)
  self.assertNotIn('restored',self.state)


class Stores(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='ikp-maint-fixture-');self.root=Path(self.tmp.name);self.root.chmod(0o700);self.db=self.root/'fixture.db'
  with sqlite3.connect(self.db) as db:db.executescript('PRAGMA application_id=1229652483;PRAGMA user_version=2;CREATE TABLE projects(id PRIMARY KEY,notes,revision);CREATE TABLE project_sources(id);CREATE TABLE project_settings(id);CREATE TABLE commands(id,payload);INSERT INTO projects VALUES(1,"human",7);INSERT INTO commands VALUES(1,x\'01\');')
  self.db.chmod(0o600);self.before=m.fingerprint(self.db)
 def tearDown(self):self.tmp.cleanup()
 def edit(self,sql):
  with sqlite3.connect(self.db) as db:db.executescript(sql)
 def test_added_projects_allowed_original_revision_preserved(self):
  self.edit('INSERT INTO projects VALUES(2,"imported",1)');m.preserved(self.before,m.fingerprint(self.db))
 def test_overwritten_manual_notes_or_revision_is_rejected(self):
  self.edit('UPDATE projects SET notes="overwrite",revision=8 WHERE id=1')
  with self.assertRaisesRegex(m.SafeFailure,'ORIGINAL_ROWS_CHANGED'):m.preserved(self.before,m.fingerprint(self.db))
 def test_new_command_is_forbidden_even_when_old_rows_survive(self):
  self.edit('INSERT INTO commands VALUES(2,x\'02\')')
  with self.assertRaisesRegex(m.SafeFailure,'NON_IMPORT_TABLE'):m.preserved(self.before,m.fingerprint(self.db))
 def test_auth_all_tables_exact_no_new_rows_allowed(self):
  self.edit('INSERT INTO projects VALUES(2,"not auth import",1)')
  with self.assertRaisesRegex(m.SafeFailure,'NON_IMPORT_TABLE'):m.preserved(self.before,m.fingerprint(self.db),auth=True)
 def test_schema_change_is_rejected(self):
  self.edit('PRAGMA user_version=3')
  with self.assertRaisesRegex(m.SafeFailure,'SCHEMA_CHANGED'):m.preserved(self.before,m.fingerprint(self.db))
 def test_duplicate_row_multiplicity_is_protected(self):
  self.edit('INSERT INTO project_sources VALUES("same");INSERT INTO project_sources VALUES("same")');before=m.fingerprint(self.db);self.edit('DELETE FROM project_sources WHERE rowid=(SELECT max(rowid) FROM project_sources)')
  with self.assertRaisesRegex(m.SafeFailure,'ORIGINAL_ROWS_CHANGED'):m.preserved(before,m.fingerprint(self.db))
 def test_wal_writer_and_open_port_fences(self):
  wal=Path(str(self.db)+'-wal');wal.touch();ops=m.WebOps(self.root/'private.log');ops.job=lambda:{'loaded':False};ops.source_write_holders=lambda p:[777] if p==wal else []
  with patch.object(m,'DATABASES',{'auth':self.db,'projects':self.db}):
   with self.assertRaisesRegex(m.SafeFailure,'UNKNOWN_DATABASE_WRITER'):ops.fence()
   ops.source_write_holders=lambda _:[]
   with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'p777\n','')):
    with self.assertRaisesRegex(m.SafeFailure,'PORT_STILL_OPEN'):ops.fence()
 def test_source_snapshot_does_not_modify_live_wal_source(self):
  db=sqlite3.connect(self.db);db.execute('PRAGMA journal_mode=WAL');db.execute('INSERT INTO projects VALUES(9,"pending in WAL",1)');db.commit()
  try:
   before=m.fingerprint(self.db);result=m.sqlite_backup(self.db,self.root/'backup',strict_foreign_keys=True);self.assertEqual(m.fingerprint(self.db),before);self.assertEqual(m.fingerprint(result['artifact']['path']),before);self.assertEqual(result['metadata']['journal_mode'],'delete')
  finally:db.close()


class FullFlow(unittest.TestCase):
 """Run controller sequencing and durable reentry with only fixture DBs and FakeWeb."""
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='ikp-full-fixture-');self.root=Path(self.tmp.name);self.root.chmod(0o700);self.ops=FakeWeb();self.output=m.private_dir(self.root/'out');self.rehearsal=m.private_dir(self.root/'rehearsal');self.databases={}
  for n,appid in (('projects',1229652483),('auth',1229652484),('hunter',1229652481),('tracking',1229652482)):
   p=self.root/(n+'.db')
   with sqlite3.connect(p) as db:db.executescript('PRAGMA application_id='+str(appid)+';PRAGMA user_version=2;CREATE TABLE projects(id PRIMARY KEY,notes,revision);CREATE TABLE project_sources(id);CREATE TABLE project_settings(id PRIMARY KEY);CREATE TABLE commands(id);INSERT INTO projects VALUES("manual","preserve notes",7);')
   p.chmod(0o600);self.databases[n]=p
  m.atomic(self.rehearsal/'before.private.json',{'tables':m.fingerprint(self.databases['projects'])['tables']})
  self.journal=self.root/'journal.json';m.atomic(self.journal,{'execution_id':EXECUTION,'owner_thread':MANAGER,'operator_thread':OWNER,'root_operates_stop':False,'stop_jobs':list(JOB_SPECS),'approved_manual_stop':MANUAL,'state':'legacy_snapshots_ready_waiting_owner_imports','migrated_domains':[],'operator_steps':{'existing':{'preserve':'original'}}})
  self.sealed=self.root/'sealed.json';m.atomic(self.sealed,{'protected_processes':{'v2_web':process(),'v2_Hunter':process(2608),'v2_Tracking':process(25225)}})
  self.planpath=self.root/'plan.json';self.plan={'initial_web':self.ops.process(101),'initial_tree':self.ops.tree(101),'initial_socket':{'path':'/private/tmp/fixture/p.sock'},'tool_source_sha256':m.sha(m.__file__),'python':'fixture-python-never-executed','code_root':str(self.root/'fixture-code'),'code_files':{m.IMPORTER:'synthetic-owner-hash'}};m.atomic(self.planpath,self.plan)
  self.apply_calls=0;self.lose_first_receipt=False;self.change_manual=False;self.stack=ExitStack()
  for name,value in {'OUTPUT':self.output,'REHEARSAL':self.rehearsal,'DATABASES':self.databases,'LEGACY_PLAN':self.sealed,'JOURNAL':self.journal}.items():self.stack.enter_context(patch.object(m,name,value))
  self.stack.enter_context(patch.object(m,'WebOps',return_value=self.ops));self.stack.enter_context(patch.object(m,'Journal',side_effect=lambda:RealJournal(self.journal)));self.stack.enter_context(patch.object(m,'immutable_inputs'));self.stack.enter_context(patch.object(m,'peer_guard',return_value={'preserved':True}));self.stack.enter_context(patch.object(m,'command',side_effect=self.owner));self.stack.enter_context(patch.object(m.subprocess,'check_output',side_effect=self.git));self.stack.enter_context(redirect_stdout(io.StringIO()))
 def tearDown(self):self.stack.close();self.tmp.cleanup()
 def git(self,argv,**_):
  if argv==['git','rev-parse','HEAD']:return 'fixture-candidate\n'
  if argv==['git','branch','--show-current']:return 'codex/integration\n'
  if argv==['git','status','--porcelain']:return ''
  if argv==['git','rev-parse','main']:return '63e8a2857241c6a76226f21435e40db9736a1e7e\n'
  self.fail('Unexpected process call: '+str(argv))
 def owner(self,argv,*_,**kwargs):
  self.assertFalse(self.ops.loaded);self.assertEqual(argv[1:3],['-m','projects_service.takeover']);self.assertNotIn('TOKEN',str(kwargs['env']));self.assertEqual(kwargs['env']['PYTHONNOUSERSITE'],'1')
  receipt=Path(argv[argv.index('--receipt')+1]);apply='--apply' in argv
  with sqlite3.connect(self.databases['projects']) as db:
   exists=db.execute('SELECT 1 FROM project_settings WHERE id="batch"').fetchone() is not None
   if apply:
    self.apply_calls+=1
    if not exists:
     db.executemany('INSERT INTO projects VALUES(?,?,1)',[(str(i),'synthetic import') for i in range(32)]);db.execute('INSERT INTO project_settings VALUES("batch")')
    if self.change_manual:db.execute('UPDATE projects SET notes="bad owner change" WHERE id="manual"')
  if apply and self.lose_first_receipt and self.apply_calls==1:raise m.SafeFailure('SIMULATED_COMMITTED_BEFORE_RECEIPT')
  result={'contract':'fixture-contract','execution_id':EXECUTION,'package_sha256':m.PACKAGE_SHA,'snapshot_sha256':'d0e25f6472aca37ff408ff4ff8219fb6953ab698e053add40dc14e7f44431d46','importer_source_sha256':'synthetic-owner-hash','replayed':exists,'mappings':[{'project_id':str(i)} for i in range(32)] if apply else [],**({k:0 for k in m.NEW_COUNTERS} if exists else m.INITIAL_COUNTERS)}
  if not apply:result['dry_run']=True
  if not receipt.exists():m.atomic(receipt,result)
  if apply:
   export=Path(argv[argv.index('--mapping')+1]);value={k:result[k] for k in ('contract','execution_id','package_sha256','snapshot_sha256','mappings')}
   if not export.exists():m.atomic(export,value)
 def execute(self,**kwargs):m.execute('fixture-candidate',self.planpath,m.sha(self.planpath),**kwargs)
 def test_success_preserves_old_journal_and_writes_no_worker(self):
  self.execute();d=m.read_json(self.journal);self.assertEqual(d['operator_steps'],{'existing':{'preserve':'original'}});self.assertEqual(d['state'],'legacy_snapshots_ready_waiting_owner_imports');self.assertEqual(d['migrated_domains'],['projects']);self.assertEqual(self.ops.actions,['bootout','bootstrap']);self.assertEqual(self.apply_calls,1)
  r=m.read_json(self.output/'final-receipt.json');self.assertTrue(r['auth_all_rows_unchanged']);self.assertEqual(r['mapping_rows'],32);self.assertFalse(r['workers_stopped']);self.assertEqual(len(r['before_online'])+len(r['stopped'])+len(r['after_import']),12)
 def test_complete_reentry_never_repeats_import_or_services(self):
  self.execute();self.execute();self.assertEqual(self.apply_calls,1);self.assertEqual(self.ops.actions,['bootout','bootstrap'])
 def test_complete_reentry_checks_nested_backup_bytes(self):
  self.execute();d=m.read_json(self.output/'final-receipt.json');m.atomic(d['after_import']['auth']['artifact']['path'],b'corrupted snapshot')
  with self.assertRaisesRegex(m.SafeFailure,'ARTIFACT_DRIFT'):self.execute()
  self.assertEqual(self.apply_calls,1)
 def test_changed_seed_restores_web_without_applying(self):
  with sqlite3.connect(self.databases['projects']) as db:db.execute('UPDATE projects SET notes="human new edit" WHERE id="manual"')
  with self.assertRaises(SystemExit):self.execute()
  self.assertTrue(self.ops.loaded);self.assertEqual(self.apply_calls,0);self.assertEqual(m.read_json(self.journal)['migrated_domains'],[])
 def test_commit_receipt_loss_recovery_and_same_package_resume(self):
  self.lose_first_receipt=True
  with self.assertRaises(SystemExit):self.execute()
  self.assertTrue(self.ops.loaded);self.assertEqual(m.read_json(self.journal)['migrated_domains'],[])
  self.plan['initial_web']=self.ops.process(self.ops.pid);self.plan['initial_tree']=self.ops.tree(self.ops.pid);m.atomic(self.planpath,self.plan)
  with self.assertRaisesRegex(m.SafeFailure,'NEW_REVIEWED_PLAN'):self.execute()
  self.execute(resume_recovered=True)
  self.assertEqual(self.ops.actions,['bootout','bootstrap','bootout','bootstrap']);self.assertEqual(self.apply_calls,2)
  with sqlite3.connect(self.databases['projects']) as db:self.assertEqual(db.execute('SELECT count(*) FROM projects').fetchone()[0],33)
  self.assertEqual(m.read_json(self.output/'projects-apply-receipt.json')['created_projects'],0)
 def test_bad_owner_original_row_change_blocks_auto_restore(self):
  self.change_manual=True
  with self.assertRaises(SystemExit):self.execute()
  self.assertFalse(self.ops.loaded);d=m.read_json(self.journal);self.assertEqual(d['migrated_domains'],[]);self.assertEqual(d['maintenance_steps'][m.PHASE]['last_failure']['recovery'],'blocked_unknown_writer_or_restore_state')
  self.assertEqual(self.ops.actions,['bootout'])
 def test_readonly_status_before_execution_never_mutates_journal(self):
  before=m.sha(self.journal);r=m.readonly_status(self.planpath,m.sha(self.planpath));self.assertEqual(r['state'],'not_started');self.assertTrue(r['website_loaded']);self.assertEqual(r['actions'],0);self.assertEqual(m.sha(self.journal),before);self.assertEqual(self.ops.actions,[])
 def test_readonly_status_unknown_stop_proves_absence_without_finishing_it(self):
  self.ops.loaded=False;self.ops.alive={};d=m.read_json(self.journal);d['maintenance_steps']={m.PHASE:{'windows':[{'stop_intent':'earlier','tree':[process()]}]}};m.atomic(self.journal,d);before=m.sha(self.journal)
  r=m.readonly_status(self.planpath,m.sha(self.planpath));self.assertTrue(r['can_reconcile_stop_on_approved_execute']);self.assertFalse(r['recorded_stopped']);self.assertEqual(m.sha(self.journal),before);self.assertEqual(self.ops.actions,[])
 def test_readonly_status_never_calls_absent_a_reparented_original(self):
  self.ops.loaded=False;self.ops.alive={102:process(102,1)};d=m.read_json(self.journal);d['maintenance_steps']={m.PHASE:{'windows':[{'stop_intent':'earlier','tree':[process(102,101)]}]}};m.atomic(self.journal,d)
  r=m.readonly_status(self.planpath,m.sha(self.planpath));self.assertEqual(r['original_tree_still_alive'],[102]);self.assertFalse(r['can_reconcile_stop_on_approved_execute']);self.assertEqual(self.ops.actions,[])


if __name__=='__main__':unittest.main()
