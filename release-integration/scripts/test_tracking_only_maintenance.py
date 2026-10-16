"""Temporary SQLite and simulated launchd only; no runtime or provider access."""
from contextlib import ExitStack,redirect_stdout
import copy
import io
import os
from pathlib import Path
import plistlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import tracking_only_maintenance as m
from takeover_operator import Journal as RealJournal,EXECUTION,MANAGER,OWNER,JOB_SPECS,MANUAL


def result(replay=False):
 return {'passed':True,'replayed':replay,'delta':{'accounts':0 if replay else 1,'tweets':0,'ledger':0,'notifications':0},'summary':{'accounts':{'input':1,'created':1},'tweets':{'input':0},'reason_counts':{},'scope':EXECUTION}}


class Fixture(unittest.TestCase):
 def setUp(self):
  self.mask=os.umask(0o077);self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='ik-tracking-ops-');self.root=Path(self.tmp.name);self.stack=ExitStack();self.native=m.private_dir(self.root/'native');self.out=m.private_dir(self.root/'out');self.databases={}
  for name,appid,version in (('tracking',0x494B0202,4),('auth',0x494B0204,2),('projects',0x494B0203,2),('hunter',0x494B0201,5)):
   p=m.private_dir(self.native/'data'/name)/(name+'.db')
   with sqlite3.connect(p) as db:
    db.executescript('PRAGMA application_id='+str(appid)+';PRAGMA user_version='+str(version)+''';CREATE TABLE runtime(id PRIMARY KEY,heartbeat,connection,pong_at);INSERT INTO runtime VALUES(1,0,'disconnected',NULL);CREATE TABLE projects(id PRIMARY KEY,notes,revision);INSERT INTO projects VALUES('manual','keep human text',7);CREATE TABLE receipts(id PRIMARY KEY,raw);CREATE TABLE tweet_ledger(id);CREATE TABLE feed_meta(singleton PRIMARY KEY,semantic_revision,last_retention_now_ms,snapshot_epoch);INSERT INTO feed_meta VALUES(1,1,10,'keep-epoch');CREATE TRIGGER inserted AFTER INSERT ON projects BEGIN UPDATE feed_meta SET semantic_revision=semantic_revision+1;END;''')
   p.chmod(0o600);self.databases[name]=p
  self.plist=m.private_dir(self.native/'agents')/(m.LABEL+'.plist');m.atomic(self.plist,plistlib.dumps({'original':True}));self.plandir=m.private_dir(self.native/'plans/tracking'/m.SOURCE);self.stack.enter_context(patch.object(m.night,'validate'));self.stack.enter_context(patch.object(m,'V2',self.native));self.stack.enter_context(patch.object(m,'OUTPUT',self.out));self.stack.enter_context(patch.object(m,'PLIST',self.plist));self.stack.enter_context(patch.object(m,'PLAN_DIR',self.plandir));self.stack.enter_context(patch.object(m,'DATABASE',self.databases['tracking']));self.stack.enter_context(patch.object(m,'DATABASES',self.databases))
  m.atomic(self.plandir/'night_worker_ops.py',Path(m.night.__file__).read_bytes());m.atomic(self.plandir/(m.LABEL+'.plist'),plistlib.dumps(m.expected_job()));m.private_dir(self.native/'jobs/tracking')
 def tearDown(self):self.stack.close();self.tmp.cleanup();os.umask(self.mask)
 def edit(self,sql):
  with sqlite3.connect(self.databases['tracking']) as db:db.execute(sql)
 def checkpoint(self,name):return m.sqlite_backup(self.databases['tracking'],m.private_dir(self.out/name),strict_foreign_keys=True)


class Core(Fixture):
 def test_zero_release_passes_and_expired_nonzero_never_cleared(self):
  m.released(self.databases['tracking']);self.edit("UPDATE runtime SET heartbeat=1")
  before=m.fingerprint(self.databases['tracking'])
  with self.assertRaisesRegex(m.SafeFailure,'NO_SQL_CLEAR'):m.released(self.databases['tracking'])
  self.assertEqual(m.fingerprint(self.databases['tracking']),before)
 def test_missing_or_connected_release_is_rejected(self):
  self.edit("UPDATE runtime SET connection='connected'")
  with self.assertRaises(m.SafeFailure):m.released(self.databases['tracking'])
  self.edit('DELETE FROM runtime')
  with self.assertRaises(m.SafeFailure):m.released(self.databases['tracking'])
 def test_zero_replay_cannot_wash_quarantined_original(self):
  m.verify_result(result());m.verify_result(result(True),replay=True)
  bad=result(True);bad['summary']['accounts']={'input':1,'quarantined':1};bad['summary']['reason_counts']={'recovery_boundary_unproven':1}
  with self.assertRaises(m.SafeFailure):m.verify_result(bad,replay=True)
 def test_boolean_count_rejected(self):
  bad=result();bad['delta']['accounts']=True
  with self.assertRaises(m.SafeFailure):m.verify_result(bad)
 def test_original_rows_and_exact_trigger_increment(self):
  cp=self.checkpoint('before');self.edit("INSERT INTO projects VALUES('new','imported',1)");self.edit('UPDATE feed_meta SET last_retention_now_ms=20');m.preserve(cp['artifact']['path'],self.databases['tracking'])
  self.edit('UPDATE feed_meta SET semantic_revision=semantic_revision+1')
  with self.assertRaisesRegex(m.SafeFailure,'FEED_META_CHANGED'):m.preserve(cp['artifact']['path'],self.databases['tracking'])
 def test_original_manual_edit_and_epoch_changes_are_rejected(self):
  cp=self.checkpoint('before');self.edit("UPDATE projects SET notes='overwritten',revision=8 WHERE id='manual'")
  with self.assertRaisesRegex(m.SafeFailure,'ORIGINAL_TRACKING_ROWS_CHANGED'):m.preserve(cp['artifact']['path'],self.databases['tracking'])
 def test_runtime_alias_is_rejected_before_copy(self):
  target=m.private_dir(self.native/'releases')/m.SOURCE;target.symlink_to(self.root/'foreign')
  with patch.object(m,'RELEASE',target):
   with self.assertRaisesRegex(ValueError,'ALIASED_PATH'):m.stage({})
  self.assertTrue(target.is_symlink())
 def test_original_entry_has_all_three_certificates_and_no_sample(self):
  plan={'python':'fixture-python','inputs':{x:{'path':'/fixture/'+x,'sha256':'a'*64}for x in ('bundle','map','ownership')},'certificates':{x:{'path':'/fixture/'+x,'sha256':'b'*64}for x in ('boundary','alias','identity')}}
  args=m.owner_args(plan,'/fixture/config',apply=True);self.assertTrue(args[1].endswith('/integration/import-takeover.py'));self.assertEqual(args[-1],'--apply')
  for name in ('boundary','alias','identity'):self.assertIn('--recovery-'+name+'-review',args);self.assertIn('--recovery-'+name+'-review-sha256',args)
  self.assertFalse(any('sample' in x for x in args))


class FakeOps:
 def __init__(self,root,database):self.root=root;self.database=database;self.loaded=True;self.pid=25225;self.alive=True;self.actions=[];self.graceful=True;self.bootstrap_unknown=False
 def identity(self):return {'pid':self.pid,'ppid':1,'uid':os.getuid(),'started_utc':'2026-10-15T00:00:00+00:00','executable':'fixture-python','cwd':str(self.root/'jobs/tracking')}
 def process(self,pid):return self.identity() if self.alive and pid==self.pid else None
 def tree(self,pid):return [self.identity()] if self.alive and pid==self.pid else []
 def job(self):return {'loaded':self.loaded,'pid':self.pid if self.loaded else None}
 def bootout(self):
  self.actions.append(('bootout',m.LABEL));self.loaded=False;self.alive=False
  if self.graceful:
   with sqlite3.connect(self.database) as db:db.execute("UPDATE runtime SET heartbeat=0,connection='disconnected',pong_at=NULL")
 def fence(self):m.require(not self.loaded,'FIXTURE_LOADED')
 def bootstrap(self):
  self.actions.append(('bootstrap','307d'))
  if self.bootstrap_unknown:raise m.SafeFailure('SIMULATED_BOOTSTRAP_UNKNOWN')
  self.pid+=1000;self.loaded=True;self.alive=True
 def ready(self,*_):m.require(self.loaded,'FIXTURE_NOT_READY')


class Flow(Fixture):
 def setUp(self):
  super().setUp();self.ops=FakeOps(self.native,self.databases['tracking']);self.calls=0;self.fail_apply=False
  self.plan={'python':'fixture-python','tool_source_sha256':m.sha(m.__file__),'initial_tracking':self.ops.identity(),'initial_tree':self.ops.tree(self.ops.pid),'initial_plist_sha256':m.sha(self.plist),'reader_plan':{'fixture':True},'protection':{'protected_processes':{'hunter':{'pid':78559},'web':{'pid':54011}}},'web_tree':[{'pid':54011},{'pid':54014}]};m.atomic(self.plandir/'worker.json',self.plan['reader_plan']);self.planpath=self.root/'plan.json';m.atomic(self.planpath,self.plan)
  self.journal=self.root/'journal.json';self.stack.enter_context(patch.object(m,'JOURNAL',self.journal));m.atomic(self.journal,{'execution_id':EXECUTION,'owner_thread':MANAGER,'operator_thread':OWNER,'root_operates_stop':False,'stop_jobs':list(JOB_SPECS),'approved_manual_stop':MANUAL,'migrated_domains':['projects','hunter'],'operator_steps':{}})
  for name,value in (('TrackingOps',lambda *_:self.ops),('Journal',lambda:RealJournal(self.journal)),('immutable',lambda *_:None),('peers',lambda *_:{'protected':True}),('stage',lambda *_:None),('verify_persisted',lambda *_:None),('command',self.command)):
   self.stack.enter_context(patch.object(m,name,value))
  self.stack.enter_context(patch.object(m.subprocess,'check_output',side_effect=self.git));self.stack.enter_context(redirect_stdout(io.StringIO()))
 def git(self,args,**_):
  return {('git','rev-parse','HEAD'):'fixture\n',('git','status','--porcelain'):'',('git','rev-parse','main'):'63e8a2857241c6a76226f21435e40db9736a1e7e\n'}[tuple(args)]
 def command(self,argv,log,*,env,stdout,**_):
  self.assertFalse(self.ops.loaded);m.released(self.databases['tracking']);self.assertNotIn('IKUN_TRACKING_6551_TOKEN',env);self.assertNotIn('TRACKING_API_TOKEN',env);self.calls+=1
  with sqlite3.connect(self.databases['tracking']) as db:
   existing=db.execute("SELECT 1 FROM projects WHERE id='new'").fetchone()
   if not existing:db.execute("INSERT INTO projects VALUES('new','imported',1)");db.execute("INSERT INTO receipts VALUES('takeover','fixture')");db.execute('UPDATE feed_meta SET last_retention_now_ms=20')
  if self.fail_apply and not existing:raise m.SafeFailure('SIMULATED_APPLY_UNKNOWN_AFTER_COMMIT')
  m.atomic(stdout,result(bool(existing)))
 def execute(self,**kwargs):
  with patch.object(m,'owner_args',return_value=['fixture-python','original-owner-entry']):m.execute('fixture',self.planpath,m.sha(self.planpath),**kwargs)
 def test_status_reads_no_runtime_database_and_does_not_write_journal(self):
  before=m.sha(self.journal);status=m.readonly_status(self.planpath,m.sha(self.planpath));self.assertEqual(status['state'],'not_started');self.assertEqual(status['runtime_database_connections'],0);self.assertEqual(m.sha(self.journal),before);self.assertEqual(self.ops.actions,[])
 def test_success_twelve_backups_only_tracking_stop_and_fixed_reader(self):
  self.execute();final=m.read_json(self.out/'final-receipt.json');self.assertEqual(sum(len(final[k])for k in ('before_online','stopped','after_import')),12);self.assertEqual(self.ops.actions,[('bootout',m.LABEL),('bootstrap','307d')]);self.assertEqual(m.read_json(self.journal)['migrated_domains'],['projects','hunter','tracking'])
 def test_repeat_completed_is_no_action(self):
  self.execute();calls=self.calls;self.execute();self.assertEqual(self.calls,calls);self.assertEqual(len(self.ops.actions),2)
 def test_nonzero_release_aborts_before_owner_and_never_clears(self):
  self.ops.graceful=False;self.edit('UPDATE runtime SET heartbeat=1')
  with self.assertRaises(SystemExit):self.execute()
  self.assertEqual(self.calls,0)
  with sqlite3.connect(self.databases['tracking']) as db:self.assertEqual(db.execute('SELECT heartbeat FROM runtime').fetchone()[0],1)
 def test_unknown_commit_recovers_fixed_reader_then_same_package_resume(self):
  self.fail_apply=True
  with self.assertRaises(SystemExit):self.execute()
  self.assertEqual(self.ops.actions,[('bootout',m.LABEL),('bootstrap','307d')]);self.plan['initial_tracking']=self.ops.identity();self.plan['initial_tree']=self.ops.tree(self.ops.pid);self.plan['initial_plist_sha256']=m.sha(self.plist);m.atomic(self.planpath,self.plan)
  self.execute(resume=True)
  with sqlite3.connect(self.databases['tracking']) as db:self.assertEqual(db.execute('SELECT count(*) FROM projects').fetchone()[0],2)
 def test_unknown_bootstrap_is_never_repeated(self):
  self.ops.bootstrap_unknown=True
  with self.assertRaises(SystemExit):self.execute()
  self.assertEqual([x for x in self.ops.actions if x[0]=='bootstrap'],[('bootstrap','307d')])


if __name__=='__main__':unittest.main()
