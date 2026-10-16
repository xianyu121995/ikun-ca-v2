"""Few offline checks for the thin input adapters, no real Alpha/provider/native jobs."""
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import patch
import sample_alpha_witness as a
import sample_tracking_inputs as t
import sample_hunter_argv as h
from takeover_backup import atomic,sha,private_dir,SafeFailure
from takeover_operator import ROOT


class SampleGlue(unittest.TestCase):
 def setUp(self):
  self.mask=os.umask(0o077);parent=private_dir(ROOT/'release-integration/.runtime/first-real-sample/local-glue-tests');self.tmp=tempfile.TemporaryDirectory(dir=parent);self.root=Path(self.tmp.name);self.root.chmod(0o700)
 def tearDown(self):self.tmp.cleanup();os.umask(self.mask)
 def test_alpha_schemas_initial_immutable_and_drift_latched(self):
  f=a.Facts(42,'2026-10-16T00:00:00+00:00',True,1000,999,3,'a'*64);p=a.Projection(f,now=1000,epoch='11111111-1111-4111-8111-111111111111',run_id='22222222-2222-4222-8222-222222222222',hunter_exclusions='b'*64,tracking_exclusions='c'*64);first=p.project(f,now=1000);self.assertEqual(len(first['hunter']),8);self.assertEqual(len(first['tracking_rolling']),6)
  drift=p.project(replace(f,reconnect_count=4),now=1000);self.assertTrue(drift['stop_new_connections']);self.assertEqual(drift['tracking_initial'],first['tracking_initial']);self.assertTrue(p.project(f,now=1000)['stop_new_connections'])
 def test_alpha_live_loop_on_fixture_only_closes_unhealthy_without_modifying_source(self):
  folder=private_dir(self.root/'alpha-source');roster=folder/'accounts.json';state=folder/'state.json';atomic(roster,{'accounts':[{'username':'fixturealpha','enabled':True}]});atomic(state,{'runtime':{'pid':42,'connected':True,'last_pong_at':time.time(),'reconnects':3}});original=sha(state);expected={'pid':42,'ppid':1,'uid':os.getuid(),'started_utc':'2026-10-16T00:00:00+00:00','executable':'fixture-python'};out=self.root/'witness'
  plan={'seconds':1,'output':str(out),'expected_process':expected,'accounts_sha256':sha(roster),'epoch':'11111111-1111-4111-8111-111111111111','hunter_run_id':'22222222-2222-4222-8222-222222222222','hunter_exclusions_sha256':'b'*64,'tracking_exclusions_sha256':'c'*64};signals={s:signal.getsignal(s)for s in (signal.SIGTERM,signal.SIGINT)}
  try:
   with patch('takeover_operator.ALPHA',state),patch('takeover_operator.System.process',return_value=expected),patch('sqlite3.connect',side_effect=AssertionError('no database in witness')):a.observe(plan)
  finally:
   for sig,handler in signals.items():signal.signal(sig,handler)
  initial=json.loads((out/'tracking.initial.json').read_text());rolling=json.loads((out/'tracking.rolling.json').read_text());self.assertTrue(initial['healthy']);self.assertFalse(rolling['healthy']);self.assertEqual(sha(state),original)
  with self.assertRaisesRegex(SafeFailure,'INITIAL_ALREADY_EXISTS'):a.observe(plan)
 def test_tracking_rejects_absent_real_late_facts_without_opening_database(self):
  static=json.loads((ROOT/'release-integration/.runtime/first-real-sample/next-stage/sample-static.private.json').read_text())
  with patch('sqlite3.connect',side_effect=AssertionError('no database without late facts')):
   with self.assertRaisesRegex(SafeFailure,'ACTUAL_LATE_RECEIPTS_REQUIRED'):t.mint(static,{})
 def test_hunter_binds_owner_canonical_bytes_and_original_cli_only(self):
  source={'python':'fixture-python','fingerprint':{'sample_source_sha256':'a'*64}};static={'hunter_source':source,'hunter_run_id':'11111111-1111-4111-8111-111111111111','target':'0x2a_ikun','alpha_initial':str(self.root/'alpha/tracking.initial.json'),'output':str(self.root/'arm/tracking')};manifest={'protocol':'hunter-sample-only-v2','run_id':static['hunter_run_id'],'hunters':[{'mode':'REST','x_handle':'0x2a_ikun','rest_phase':'baseline_only'},{'mode':'WSS','x_handle':'fixtureowned','rest_phase':None}]};canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();gates={'manifest_sha256':hashlib.sha256(canonical(manifest)).hexdigest(),'sample_source_sha256':'a'*64};index={}
  for key in h.REQUIRED:
   path=self.root/(key+'.json');atomic(path,manifest if key=='manifest'else gates if key=='gates'else {'synthetic_source_only':True});index[key]={'path':str(path),'sha256':sha(path)}
  value=h.bind(static,index);argv=json.loads(Path(value['run_argv']['path']).read_text());self.assertEqual(argv[:4],['fixture-python','-m','hunterradar.sample_only','run']);self.assertIn('--offline-confirmed',argv);self.assertEqual((self.root/'arm/hunter/manifest.json').read_bytes(),canonical(manifest));self.assertFalse(value['temporary_secrets_materialized'])
 def test_hunter_missing_owner_receipts_never_fabricates_input(self):
  with self.assertRaisesRegex(SafeFailure,'REAL_HUNTER_OWNER_ARTIFACTS_REQUIRED'):h.bind({},{} )

 def add_fixture(self):
  before=[{'id':'old','twAccount':'fixtureold','newTweetBol':True,'newTweetQuoteBol':False,'newFlwBol':False}];request={'method':'POST','endpoint':'twitter_watch_add','root_review_sha':'a'*40,'body':{'username':'0x2a_ikun','groupName':'test-group','newTweetBol':True,'newTweetQuoteBol':True,'newFlwBol':False}};created={'success':True,'data':{'id':'new','twGroupId':42}};return before,request,created
 def test_one_setup_read_builds_expected_proof_from_actual_add_not_snapshot(self):
  before,request,created=self.add_fixture();watch=t.expected_new_watch('0x2a_ikun',before,created,request);self.assertEqual(watch['id'],'new');self.assertEqual(watch['twGroupId'],42);self.assertNotIn('watch_after',t.LATE);self.assertIn('watch_request',t.LATE)
 def test_add_id_only_blocks_without_inventing_assigned_group(self):
  before,request,created=self.add_fixture();created['data'].pop('twGroupId')
  with self.assertRaisesRegex(SafeFailure,'ASSIGNED_GROUP_UNPROVEN'):t.expected_new_watch('0x2a_ikun',before,created,request)
 def test_missing_expected_flag_blocks_without_guessing_false(self):
  before,request,created=self.add_fixture();before[0]['newUnFlwBol']=False
  with self.assertRaisesRegex(SafeFailure,'EXPECTED_FLAGS_INCOMPLETE'):t.expected_new_watch('0x2a_ikun',before,created,request)


if __name__=='__main__':unittest.main()
