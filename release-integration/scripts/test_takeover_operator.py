#!/usr/bin/env python3
"""Only synthetic launchd/process substitutes and independent temporary PostgreSQL clusters."""
import copy
import io
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch
import psycopg
from psycopg.conninfo import make_conninfo
import takeover_backup as b
import takeover_operator as o
TEST_OUTPUT=None
@contextmanager
def preserved_pg_fixture():
 root=b.private_dir((TEST_OUTPUT or o.ROOT/'release-integration/.runtime/takeover-operator-tests')/('pg-fixture-'+str(time.time_ns())))
 yield str(root)

def identity(pid,*,parent=1,cwd='/fixture'):
 return {'pid':pid,'ppid':parent,'uid':os.getuid(),'started_utc':'2026-10-10T10:33:40+00:00','executable':'fixture-python','cwd':cwd}

class FakeSystem:
 def __init__(self):
  self.alive={s['pid']:identity(s['pid']) for s in o.JOB_SPECS.values()};self.alive[6466]=identity(6466,parent=6465,cwd=str(o.HUNTER));self.alive[6465]=identity(6465)
  self.loaded={k:True for k in o.JOB_SPECS};self.overrides={k:None for k in o.JOB_SPECS};self.actions=[];self.extra=[];self.add_protected_after_disable=False
 def process(self,pid):return copy.deepcopy(self.alive.get(pid))
 def job(self,label):return {'loaded':self.loaded[label],'pid':o.JOB_SPECS[label]['pid'] if self.loaded[label] else None}
 def disabled(self,label):return self.overrides[label]
 def tree(self,pid):return [self.process(pid),*self.extra]
 def disable(self,label):
  self.actions.append(('disable',label));self.overrides[label]=True
  if self.add_protected_after_disable:self.extra=[identity(9034)]
 def bootout(self,label):self.actions.append(('bootout',label));self.loaded[label]=False;self.alive.pop(o.JOB_SPECS[label]['pid'],None)
 def sigterm_hunter(self,expected):
  assert o.same_process(self.process(6466),expected);self.actions.append(('SIGTERM',6466));self.alive.pop(6466)

class OperatorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='ikt-op-test-',dir='/private/tmp');self.root=Path(self.tmp.name);self.root.chmod(0o700);self.system=FakeSystem();self.path=self.root/'journal.json'
  self.data={'execution_id':o.EXECUTION,'owner_thread':o.MANAGER,'operator_thread':o.OWNER,'root_operates_stop':False,'stop_jobs':list(o.JOB_SPECS),'approved_manual_stop':o.MANUAL,'state':'preflight','stopped_jobs':[],'real_sample_executed':False,'migrated_domains':[]};b.atomic(self.path,self.data)
  self.plan={'jobs':{},'manual_hunter':self.system.process(6466)}
  for label,spec in o.JOB_SPECS.items():
   p=self.root/(label+'.plist');b.atomic(p,b'synthetic plist');self.plan['jobs'][label]={'process':self.system.process(spec['pid']),'plist':str(p),'plist_sha256':b.sha(p)}
 def tearDown(self):self.tmp.cleanup()
 def test_journal_owner_mismatch(self):
  r=copy.deepcopy(self.data);r['operator_thread']='different';b.atomic(self.path,r)
  with self.assertRaises(b.SafeFailure):
   with o.Journal(self.path):pass
 def test_journal_rejects_extra_label(self):
  r=copy.deepcopy(self.data);r['stop_jobs'].append('ca.alpha');b.atomic(self.path,r)
  with self.assertRaises(b.SafeFailure):
   with o.Journal(self.path):pass
 def test_journal_lock_excludes_second_operator(self):
  with o.Journal(self.path):
   with self.assertRaisesRegex(b.SafeFailure,'ANOTHER_OPERATOR_ACTIVE'):
    with o.Journal(self.path):pass
 def test_journal_preserves_concurrent_root_write(self):
  with o.Journal(self.path) as j:
   changed={**self.data,'root_extra':'preserve'};b.atomic(self.path,changed)
   with self.assertRaisesRegex(b.SafeFailure,'JOURNAL_CONCURRENT_CHANGE'):j.save()
   self.assertEqual(b.read_json(self.path)['root_extra'],'preserve')
 def test_two_calls_stop_only_once(self):
  label=next(iter(o.JOB_SPECS))
  with o.Journal(self.path) as j:o.stop_job_once(j,self.system,label,self.plan);o.stop_job_once(j,self.system,label,self.plan)
  self.assertEqual(self.system.actions,[('disable',label),('bootout',label)])
 def test_pid_reuse_fails_before_disable(self):
  label=next(iter(o.JOB_SPECS));self.system.alive[46545]['started_utc']='different'
  with o.Journal(self.path) as j:
   with self.assertRaises(b.SafeFailure):o.stop_job_once(j,self.system,label,self.plan)
  self.assertEqual(self.system.actions,[])
 def test_cwd_drift_fails_before_disable(self):
  label=next(iter(o.JOB_SPECS));self.system.alive[46545]['cwd']='/wrong'
  with o.Journal(self.path) as j:
   with self.assertRaises(b.SafeFailure):o.stop_job_once(j,self.system,label,self.plan)
  self.assertEqual(self.system.actions,[])
 def test_bootout_unknown_unloaded_reconciles_without_second_action(self):
  label=next(iter(o.JOB_SPECS));self.system.loaded[label]=False;self.system.alive.pop(46545);self.system.overrides[label]=True
  with o.Journal(self.path) as j:
   j.mark('stop_job:'+label,{'state':'in_progress','bootout_intent':'earlier','tree':[self.plan['jobs'][label]['process']],'previous_disabled_override':None});o.stop_job_once(j,self.system,label,self.plan)
  self.assertEqual(self.system.actions,[])
 def test_bootout_unknown_loaded_is_not_retried(self):
  label=next(iter(o.JOB_SPECS))
  with o.Journal(self.path) as j:
   j.mark('stop_job:'+label,{'state':'in_progress','bootout_intent':'earlier','tree':[]})
   with self.assertRaisesRegex(b.SafeFailure,'NO_AUTOMATIC_RETRY'):o.stop_job_once(j,self.system,label,self.plan)
  self.assertEqual(self.system.actions,[])
 def test_confirmed_disable_is_not_repeated(self):
  label=next(iter(o.JOB_SPECS));self.system.overrides[label]=True
  with o.Journal(self.path) as j:
   j.mark('stop_job:'+label,{'state':'in_progress','disable_intent':'earlier','tree':[self.plan['jobs'][label]['process']],'previous_disabled_override':None});o.stop_job_once(j,self.system,label,self.plan)
  self.assertEqual(self.system.actions,[('bootout',label)])
 def test_protected_descendant_blocks_all_job_actions(self):
  for pid in (9034,79494,6465,6466):
   self.system=FakeSystem();self.system.extra=[identity(pid)]
   with o.Journal(self.path) as j:
    with self.assertRaisesRegex(b.SafeFailure,'PROTECTED_PROCESS_IN_STOP_TREE'):o.stop_job_once(j,self.system,next(iter(o.JOB_SPECS)),self.plan)
   self.assertEqual(self.system.actions,[])
 def test_new_protected_descendant_blocks_bootout(self):
  label=next(iter(o.JOB_SPECS));self.system.add_protected_after_disable=True
  with o.Journal(self.path) as j:
   with self.assertRaisesRegex(b.SafeFailure,'PROTECTED_PROCESS_IN_STOP_TREE'):o.stop_job_once(j,self.system,label,self.plan)
  self.assertEqual(self.system.actions,[('disable',label)])
 def test_manual_sigterm_once_parent_never_signalled(self):
  with o.Journal(self.path) as j:o.stop_manual_once(j,self.system,self.plan);o.stop_manual_once(j,self.system,self.plan)
  self.assertEqual(self.system.actions,[('SIGTERM',6466)]);self.assertIn(6465,self.system.alive)
 def test_manual_cwd_drift_no_signal(self):
  self.system.alive[6466]['cwd']='/not-hunter'
  with o.Journal(self.path) as j:
   with self.assertRaises(b.SafeFailure):o.stop_manual_once(j,self.system,self.plan)
  self.assertEqual(self.system.actions,[])
 def test_pending_sigterm_no_second_signal(self):
  with o.Journal(self.path) as j:
   j.mark('manual_sigterm:6466',{'state':'in_progress','signal_intent':'earlier'})
   with self.assertRaisesRegex(b.SafeFailure,'NO_AUTOMATIC_RETRY'):o.stop_manual_once(j,self.system,self.plan)
  self.assertEqual(self.system.actions,[])
 def test_same_pid_start_reparented_is_still_alive_no_second_signal(self):
  self.system.alive[6466]['ppid']=1
  self.assertFalse(o.same_process(self.system.process(6466),self.plan['manual_hunter']))
  self.assertFalse(o.original_absent(self.system,self.plan['manual_hunter']))
  with o.Journal(self.path) as j:
   j.mark('manual_sigterm:6466',{'state':'in_progress','signal_intent':'earlier'})
   with self.assertRaisesRegex(b.SafeFailure,'NO_AUTOMATIC_RETRY'):o.stop_manual_once(j,self.system,self.plan)
  self.assertEqual(self.system.actions,[])
 def test_sigterm_unknown_but_original_absent_reconciles(self):
  self.system.alive.pop(6466)
  with o.Journal(self.path) as j:j.mark('manual_sigterm:6466',{'state':'in_progress','signal_intent':'earlier'});o.stop_manual_once(j,self.system,self.plan)
  self.assertEqual(self.system.actions,[])
 def test_done_step_checks_original_backups_not_just_receipt(self):
  payload=self.root/'db.backup';b.atomic(payload,b'original');receipt=self.root/'receipt';b.atomic(receipt,{'nested':[{'artifact':b.artifact(payload)}]})
  with o.Journal(self.path) as j:
   j.mark('backup',{'state':'done','receipt':b.artifact(receipt)});b.atomic(payload,b'corrupted')
   with self.assertRaises(b.SafeFailure):o.run_step(j,'backup',lambda _:self.fail('must never redo'))
 def test_recursive_artifact_missing_blocks(self):
  payload=self.root/'archive';b.atomic(payload,b'data');row={'deep':{'dump':b.artifact(payload)}};payload.unlink()
  with self.assertRaises((OSError,b.SafeFailure)):b.validate_artifacts(row)
 def test_failed_handle_query_does_not_prove_source_quiescent(self):
  with patch.object(o.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','permission denied')):
   with self.assertRaisesRegex(b.SafeFailure,'SOURCE_HANDLE_QUERY_FAILED'):o.System(self.root/'commands.log').source_write_holders(self.root/'source.db')
 def test_sqlite_live_wal_snapshot_sealed_destination_only(self):
  source=self.root/'source.db';db=sqlite3.connect(source);db.execute('pragma journal_mode=WAL');db.execute('create table events(id integer primary key,body text)');db.execute("insert into events values(1,'synthetic')");db.commit()
  original=b.sha(source);result=b.sqlite_backup(source,self.root/'backup');target=Path(result['artifact']['path'])
  self.assertEqual(b.sha(source),original);self.assertEqual(db.execute('pragma journal_mode').fetchone()[0],'wal');self.assertEqual(result['metadata']['tables']['events'],1);self.assertEqual(result['metadata']['journal_mode'],'delete');self.assertFalse(Path(str(target)+'-wal').exists());self.assertFalse(Path(str(target)+'-shm').exists());db.close()
 def test_sqlite_source_alias_refused(self):
  source=self.root/'source.db';sqlite3.connect(source).close();os.link(source,self.root/'alias')
  with self.assertRaisesRegex(b.SafeFailure,'SOURCE_ALIAS'):b.sqlite_backup(source,self.root/'backup')
 def test_sqlite_busy_deadline_preserves_partial_and_source(self):
  source=self.root/'busy.db';db=sqlite3.connect(source);db.execute('create table sample(id)');db.commit();db.execute('begin exclusive');db.execute('insert into sample values(1)')
  try:
   with self.assertRaisesRegex(b.SafeFailure,'SQLITE_BACKUP_DEADLINE'):b.sqlite_backup(source,self.root/'backup',timeout_seconds=.1)
   self.assertTrue((self.root/'backup/snapshot.partial').is_file());self.assertFalse((self.root/'backup/receipt.json').exists())
  finally:db.rollback();db.close()
  with sqlite3.connect(source) as check:self.assertEqual(check.execute('select count(*) from sample').fetchone()[0],0)
 def test_sqlite_prepared_resume_keeps_original_snapshot(self):
  source=self.root/'source.db';db=sqlite3.connect(source);db.execute('create table sample(id)');db.execute('insert into sample values(1)');db.commit();directory=self.root/'backup';first=b.sqlite_backup(source,directory)
  (directory/'receipt.json').unlink();Path(first['artifact']['path']).rename(directory/'snapshot.partial');db.execute('insert into sample values(2)');db.commit();resumed=b.sqlite_backup(source,directory);db.close();self.assertEqual(resumed['metadata']['tables']['sample'],1)
 def test_raw_legacy_fk_preserved_but_v2_requires_clean(self):
  source=self.root/'source.db'
  with sqlite3.connect(source) as db:db.executescript('create table parent(id primary key);create table child(pid references parent(id));insert into child values(99);')
  result=b.sqlite_backup(source,self.root/'legacy');self.assertEqual(result['metadata']['foreign_key_violations'],1)
  with self.assertRaisesRegex(b.SafeFailure,'V2_SQLITE_FK_FAILED'):b.sqlite_backup(source,self.root/'v2',strict_foreign_keys=True)
 def test_libpq_dsn_parser_preserves_quoted_secret_without_cli(self):
  password='synthetic space quote \' slash \\';dsn=make_conninfo(host='127.0.0.1',port=55432,dbname='synthetic db',user='synthetic',password=password);files=[]
  for n in ('module','import'):p=self.root/(n+'.dsn');b.atomic(p,dsn.encode());files.append(p)
  config=self.root/'config.json';b.atomic(config,dict(zip(('module_dsn_file','import_dsn_file'),map(str,files))));params=b.source_pg_params(config);self.assertEqual(params['password'],password);params['passfile']=b.empty_pgpass(self.root);env=b.pg_env(params,readonly=True);self.assertEqual(env['PGPASSWORD'],password);self.assertIn('default_transaction_read_only=on',env['PGOPTIONS']);self.assertEqual(Path(env['PGPASSFILE']).read_bytes(),b'')
 def pinned_fixture(self):
  path=self.root/'existing.env';body=b'OTHER=ignored\nDATABASE_URL="postgresql://web3:synthetic%20space%27@127.0.0.1:55432/synthetic%20db"\n';b.atomic(path,body)
  return {'path':str(path),'sha256':b.sha(path),'user':'web3'},{'host':'127.0.0.1','port':'55432','dbname':'synthetic db','user':'module','password':'synthetic-module'}
 def test_pinned_database_url_only_preserves_encoded_secret(self):
  spec,baseline=self.pinned_fixture();params=b.pinned_pg_params(spec,baseline)
  self.assertEqual(params['password'],"synthetic space'");self.assertEqual(params['dbname'],baseline['dbname']);self.assertEqual(set(params),{'host','port','dbname','user','password'})
 def test_pinned_database_url_rejects_different_database(self):
  spec,baseline=self.pinned_fixture();baseline['dbname']='other'
  with self.assertRaisesRegex(b.SafeFailure,'ENDPOINT_DATABASE_MISMATCH'):b.pinned_pg_params(spec,baseline)
 def test_pinned_database_url_rejects_source_hash_alias_and_permissions(self):
  spec,baseline=self.pinned_fixture();path=Path(spec['path']);path.write_bytes(path.read_bytes()+b'# changed\n')
  with self.assertRaisesRegex(b.SafeFailure,'SOURCE_HASH'):b.pinned_pg_params(spec,baseline)
  spec['sha256']=b.sha(path);path.chmod(0o644)
  with self.assertRaisesRegex(b.SafeFailure,'SOURCE_IDENTITY'):b.pinned_pg_params(spec,baseline)
  path.chmod(0o600);alias=self.root/'alias.env';alias.symlink_to(path);spec['path']=str(alias)
  with self.assertRaisesRegex(b.SafeFailure,'SOURCE_IDENTITY'):b.pinned_pg_params(spec,baseline)
 def test_pinned_database_url_rejects_duplicate_key(self):
  spec,baseline=self.pinned_fixture();path=Path(spec['path']);path.write_bytes(path.read_bytes()+path.read_bytes());spec['sha256']=b.sha(path)
  with self.assertRaisesRegex(b.SafeFailure,'EXACTLY_ONE'):b.pinned_pg_params(spec,baseline)
 def test_role_selection_only_two_existing_roles_and_readonly(self):
  spec,baseline=self.pinned_fixture()
  for pinned_enough in (True,False):
   calls=[];queries=[]
   class Connection:
    def __init__(self,enough):self.enough=enough
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def transaction(self):return self
    def execute(self,query):
     queries.append(query)
     result=(self.enough,False) if 'has_table_privilege' in query else (True,)
     return type('Cursor',(),{'fetchone':lambda _:result})()
   def connect(**params):
    calls.append(params['user']);self.assertIn('default_transaction_read_only=on',params['options']);self.assertTrue(params['autocommit']);return Connection(pinned_enough and params['user']=='web3')
   with patch('psycopg.connect',side_effect=connect):
    if pinned_enough:
     params,strategy=b.select_source_role(baseline,self.root/'role.log',backup_role_source=spec);self.assertEqual(params['user'],'web3');self.assertEqual(strategy,'pinned_existing_web3_readonly_backup')
    else:
     with self.assertRaisesRegex(b.SafeFailure,'PG_FULL_BACKUP_READONLY_ROLE_UNAVAILABLE'):b.select_source_role(baseline,self.root/'role.log',backup_role_source=spec)
   self.assertEqual(calls,['module','web3']);self.assertEqual(queries.count('SET TRANSACTION READ ONLY'),2);self.assertTrue(all(q=='SET TRANSACTION READ ONLY' or q.startswith('select ') for q in queries))
 def test_restore_old_port_rejected_before_connect(self):
  socket=Path(tempfile.mkdtemp(prefix='iktpg-',dir='/private/tmp'));socket.chmod(0o700)
  try:
   with patch('psycopg.connect') as connect:
    with self.assertRaisesRegex(b.SafeFailure,'OLD_PORT'):b.assert_drill_connection({'host':str(socket),'port':'55432'},self.root)
    connect.assert_not_called()
  finally:socket.rmdir()
 def test_unknown_pg_start_with_pid_is_cleaned_without_old_cluster(self):
  directory=self.root/'drill';calls=[]
  def command(args,*_,**__):
   args=list(map(str,args));calls.append(args)
   if 'initdb' in args[0]:(directory/'pgdata').mkdir()
   if args[0].endswith('pg_ctl') and args[-1]=='start':
    options=shlex.split(args[args.index('-o')+1]);socket=options[options.index('-k')+1];(directory/'pgdata/postmaster.pid').write_text('999991\n'+str(directory/'pgdata')+'\n0\n65432\n'+socket+'\n');raise b.SafeFailure('SYNTHETIC_START_RESULT_UNKNOWN')
   if args[-1]=='stop':(directory/'pgdata/postmaster.pid').unlink()
  with patch.object(b,'command',side_effect=command):
   with self.assertRaisesRegex(b.SafeFailure,'SYNTHETIC_START_RESULT_UNKNOWN'):b.postgres_restore({},directory,Path('/fixture'),protected_pids=[79494])
  self.assertEqual(sum(args[-1]=='start' for args in calls),1);self.assertEqual(sum(args[-1]=='stop' for args in calls),1);self.assertTrue(b.read_json(directory/'server-state.json')['stopped'])
 def test_protected_pid_from_unknown_pg_start_never_stopped(self):
  directory=self.root/'drill';calls=[]
  def command(args,*_,**__):
   args=list(map(str,args));calls.append(args)
   if 'initdb' in args[0]:(directory/'pgdata').mkdir()
   if args[-1]=='start':
    options=shlex.split(args[args.index('-o')+1]);socket=options[options.index('-k')+1];(directory/'pgdata/postmaster.pid').write_text('79494\n'+str(directory/'pgdata')+'\n0\n65432\n'+socket+'\n');raise b.SafeFailure('UNKNOWN')
  with patch.object(b,'command',side_effect=command):
   with self.assertRaisesRegex(b.SafeFailure,'DRILL_STOP_IDENTITY_FAILED'):b.postgres_restore({},directory,Path('/fixture'),protected_pids=[79494])
  self.assertEqual(sum(args[-1]=='stop' for args in calls),0)

class PostgresRoundtrip(unittest.TestCase):
 def test_real_custom_dump_decode_restore_on_independent_clusters(self):
  with preserved_pg_fixture() as temporary:
   root=Path(temporary);root.chmod(0o700);pgbin=Path('/opt/homebrew/bin');data=root/'source-data';log=root/'source.log';socket=Path(tempfile.mkdtemp(prefix='iktpg-',dir='/private/tmp'));socket.chmod(0o700);started=False
   params={'host':str(socket),'port':'65431','dbname':'postgres','user':'lvlei','passfile':b.empty_pgpass(root)}
   try:
    b.command([pgbin/'initdb','-D',data,'-A','trust','--encoding=UTF8','--no-locale'],log)
    options=shlex.join(['-k',str(socket),'-p','65431','-c','listen_addresses=','-c','shared_buffers=32MB','-c','max_connections=8'])
    b.command([pgbin/'pg_ctl','-D',data,'-l',root/'source-server.log','-o',options,'-w','start'],log);started=True
    with psycopg.connect(**params) as conn:
     conn.execute('create table synthetic_parent(id bigint primary key, notes text)');conn.execute('create table synthetic_child(id integer primary key,pid bigint references synthetic_parent(id))');conn.execute('insert into synthetic_parent values(%s,%s)',(9223372036854775807,'仅隔离夹具 😀'));conn.execute('insert into synthetic_child values(1,9223372036854775807)')
    dump=b.postgres_dump(params,root/'dump',pgbin);self.assertEqual(dump['table_count'],2);self.assertTrue(Path(dump['decoded_sql']['path']).is_file());result=b.postgres_restore(dump,root/'restore',pgbin,protected_pids=list(o.PROTECTED.values())+[6465,6466,46545,38618]);self.assertTrue(result['counts_match']);self.assertEqual(result['table_count'],2);self.assertTrue(b.read_json(root/'restore/server-state.json')['stopped'])
    b.validate_artifacts(dump)
   finally:
    if started:
     lines=(data/'postmaster.pid').read_text().splitlines();self.assertEqual(Path(lines[1]).resolve(),data.resolve());self.assertEqual(lines[3],'65431');self.assertNotIn(int(lines[0]),list(o.PROTECTED.values())+[6465,6466,46545,38618]);b.command([pgbin/'pg_ctl','-D',data,'-m','fast','-w','stop'],log)
    if socket.exists():socket.rmdir()

def main():
 global TEST_OUTPUT
 os.umask(0o077);directory=b.private_dir(o.ROOT/'release-integration/.runtime/takeover-operator-tests'/('run-'+str(time.time_ns())));log=directory/'tests.log'
 TEST_OUTPUT=directory
 with os.fdopen(os.open(log,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__)))
 receipt={'state':'PASS' if result.wasSuccessful() else 'FAIL','tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'real_legacy_service_actions':0,'real_legacy_database_connections':0,'real_platform_calls':0,'real_pg_roundtrip':'new isolated fixture only','log':b.artifact(log)};b.atomic(directory/'receipt.json',receipt);print(json.dumps({'state':receipt['state'],'tests':result.testsRun,'receipt':str(directory/'receipt.json')}));raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()
