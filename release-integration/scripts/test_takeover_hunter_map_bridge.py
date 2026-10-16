#!/usr/bin/env python3
"""Synthetic files only; no domain database, process control, or network."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import takeover_hunter_map_bridge as m

class BridgeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='ikun-map-fixture-',dir='/private/tmp');self.root=Path(self.tmp.name);self.root.chmod(0o700)
  self.archive=self.root/'source.dump';self.put(self.archive,b'synthetic archive')
  self.export={'contract':'ikun-projects-takeover-v1','execution_id':m.EXECUTION,'package_sha256':'a'*64,'snapshot_sha256':m.digest(self.archive),'mappings':[self.row('old1','2001')]}
  self.receipt={**copy.deepcopy(self.export),'replayed':False,'importer_source_sha256':'e'*64,'counts':{}}
  self.manifest={'contract':'ikun-takeover-source-manifest-v1','execution_id':m.EXECUTION,'scope':'ikun-main','status':'legacy_sources_stopped_final_copies_verified','postgres':{'archive':{'path':str(self.archive),'sha256':m.digest(self.archive),'bytes':self.archive.stat().st_size}}}
 def tearDown(self):self.tmp.cleanup()
 def put(self,path,value):
  path=Path(path);path.write_bytes(value if isinstance(value,bytes) else m.canonical(value));path.chmod(0o600);return path
 def row(self,legacy,xid,**changes):return {'source_system':'ikun-legacy-pg','table':'public.projects','legacy_id':legacy,'source_sha256':'b'*64,'project_id':'prj_11111111-1111-4111-8111-111111111111','x_user_id':xid,**changes}
 def args(self):
  export=self.put(self.root/'export.json',self.export);receipt=self.put(self.root/'owner-receipt.json',self.receipt);manifest=self.put(self.root/'manifest.json',self.manifest)
  return dict(projects_export=str(export),export_sha=m.digest(export),projects_receipt=str(receipt),receipt_sha=m.digest(receipt),source_manifest=str(manifest),manifest_sha=m.digest(manifest),package_sha='a'*64,importer_sha='e'*64,output=str(self.root/'out'))
 def sync_receipt(self):self.receipt.update(copy.deepcopy(self.export))
 def test_only_public_projects_verified_nonempty_x_and_original_source_hash(self):
  self.export['mappings'] += [self.row('old2',None),self.row('research','9999',table='public.research_records')];self.sync_receipt();args=self.args();result=m.bridge(**args)
  out=json.loads((self.root/'out/hunter-project-map.json').read_text());self.assertEqual(out['items'],[{'x_user_id':'2001','project_id':self.export['mappings'][0]['project_id'],'source_hash':'b'*64}]);self.assertEqual(result['counts'],{'source_rows':3,'hunter_items':1,'hunter_unresolved_x':1,'non_project_rows_excluded':1});self.assertFalse((self.root/'out/tracking-canonical-map.json').exists());self.assertEqual(result['state'],'PREPARED_FILE_MAPS_ONLY')
 def test_empty_verified_mapping_is_valid_without_guessing(self):
  self.export['mappings'][0]['x_user_id']=None;self.sync_receipt();m.bridge(**self.args());self.assertEqual(json.loads((self.root/'out/hunter-project-map.json').read_text())['items'],[])
 def test_source_alias_rejected(self):
  self.export['mappings'][0]['source_system']='legacy-pg';self.sync_receipt()
  with self.assertRaisesRegex(m.BridgeError,'UNSUPPORTED_MAPPING_SOURCE'):m.bridge(**self.args())
 def test_dump_and_manifest_hash_are_distinct(self):
  args=self.args();self.export['snapshot_sha256']=args['manifest_sha'];self.sync_receipt()
  with self.assertRaisesRegex(m.BridgeError,'DUMP_HASH_IS_NOT_MANIFEST_HASH'):m.bridge(**self.args())
 def test_owner_receipt_must_match_export(self):
  self.receipt['mappings'][0]['source_sha256']='c'*64
  with self.assertRaisesRegex(m.BridgeError,'OWNER_RECEIPT_EXPORT_MISMATCH'):m.bridge(**self.args())
 def test_dry_run_receipt_cannot_publish_mapping(self):
  self.receipt['dry_run']=True
  with self.assertRaisesRegex(m.BridgeError,'PERSISTED_OWNER_RECEIPT_REQUIRED'):m.bridge(**self.args())
 def test_importer_source_is_pinned(self):
  self.receipt['importer_source_sha256']='d'*64
  with self.assertRaisesRegex(m.BridgeError,'PERSISTED_OWNER_RECEIPT_REQUIRED'):m.bridge(**self.args())
 def test_duplicate_legacy_reference_is_not_silently_deduplicated(self):
  self.export['mappings'].append(copy.deepcopy(self.export['mappings'][0]));self.sync_receipt()
  with self.assertRaisesRegex(m.BridgeError,'DUPLICATE_LEGACY_REFERENCE'):m.bridge(**self.args())
 def test_duplicate_x_identity_is_ambiguous_even_with_same_project(self):
  self.export['mappings'].append(self.row('old2','2001'));self.sync_receipt()
  with self.assertRaisesRegex(m.BridgeError,'AMBIGUOUS_X_MAPPING'):m.bridge(**self.args())
 def test_noncanonical_id_rejected(self):
  for bad in ('name','prj_11111111-1111-1111-8111-111111111111','prj_11111111-1111-4111-8111-11111111111A'):
   self.export['mappings'][0]['project_id']=bad;self.sync_receipt()
   with self.assertRaisesRegex(m.BridgeError,'INVALID_CANONICAL_ID'):m.bridge(**self.args())
 def test_extra_raw_or_handle_field_rejected(self):
  self.export['mappings'][0]['handle']='PRIVATE_SENTINEL';self.sync_receipt()
  with self.assertRaisesRegex(m.BridgeError,'UNSUPPORTED_MAPPING_ROW'):m.bridge(**self.args())
 def test_input_permissions_symlink_and_hardlink_rejected(self):
  args=self.args();path=Path(args['projects_export']);path.chmod(0o644)
  with self.assertRaisesRegex(m.BridgeError,'PRIVATE_REGULAR_INPUT_REQUIRED'):m.bridge(**args)
  path.chmod(0o600);alias=self.root/'alias.json';alias.symlink_to(path);args['projects_export']=str(alias)
  with self.assertRaisesRegex(m.BridgeError,'PRIVATE_REGULAR_INPUT_REQUIRED'):m.bridge(**args)
  alias.unlink();os.link(path,alias);args['projects_export']=str(path)
  with self.assertRaisesRegex(m.BridgeError,'PRIVATE_REGULAR_INPUT_REQUIRED'):m.bridge(**args)
 def test_changed_input_hash_rejected(self):
  args=self.args();self.put(args['projects_export'],b'{}')
  with self.assertRaisesRegex(m.BridgeError,'INPUT_HASH_MISMATCH'):m.bridge(**args)
 def test_duplicate_json_and_nonfinite_rejected(self):
  for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
   p=self.put(self.root/'bad.json',raw)
   with self.assertRaises(m.BridgeError):m.read_json(p,m.digest(p))
 def test_replay_and_changed_output_never_overwrite(self):
  args=self.args();first=m.bridge(**args);before=m.digest(self.root/'out/bridge-receipt.json');again=m.bridge(**args);self.assertEqual(again['state'],'REPLAY_NO_ACTION');self.assertEqual(before,again['receipt_sha256']);self.put(self.root/'out/hunter-project-map.json',b'changed')
  with self.assertRaisesRegex(m.BridgeError,'EXISTING_BRIDGE_OUTPUT_DRIFT'):m.bridge(**args)
  self.assertEqual((self.root/'out/hunter-project-map.json').read_bytes(),b'changed');self.assertEqual(before,m.digest(self.root/'out/bridge-receipt.json'))
 def test_partial_output_preserved_for_review(self):
  args=self.args();out=self.root/'out';out.mkdir(mode=0o700);self.put(out/'hunter-project-map.json',b'partial')
  with self.assertRaisesRegex(m.BridgeError,'PARTIAL_OR_UNKNOWN_OUTPUT'):m.bridge(**args)
  self.assertEqual((out/'hunter-project-map.json').read_bytes(),b'partial')
 def test_source_archive_drift_rejected(self):
  args=self.args();self.put(self.archive,b'changed')
  with self.assertRaisesRegex(m.BridgeError,'SOURCE_ASSET_DRIFT'):m.bridge(**args)
 def test_cli_error_contains_no_private_payload(self):
  args=self.args();self.put(args['projects_export'],b'PRIVATE_SENTINEL');argv=[sys.executable,str(Path(m.__file__))]
  for key,value in args.items():argv+=['--'+key.replace('_','-'),value]
  result=subprocess.run(argv,capture_output=True,text=True);self.assertEqual(result.returncode,2);self.assertNotIn('PRIVATE_SENTINEL',result.stdout+result.stderr);self.assertIn('INPUT_HASH_MISMATCH',result.stderr)

def main():
 os.umask(0o077);directory=Path(__file__).resolve().parents[2]/'release-integration/.runtime/v2-maintenance/bridge-tests'/('run-'+str(time.time_ns()));directory.mkdir(parents=True,mode=0o700);log=directory/'tests.log'
 with log.open('w') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BridgeTests))
 log.chmod(0o600);receipt={'state':'PASS' if result.wasSuccessful() else 'FAIL','tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'converter_sha256':m.digest(m.__file__),'log_sha256':m.digest(log),'runtime_database_access':False,'real_provider_calls':0,'fixtures_only':True};path=directory/'receipt.json';path.write_bytes(m.canonical(receipt));path.chmod(0o600);print(json.dumps({**receipt,'receipt':str(path)}));raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__':main()
