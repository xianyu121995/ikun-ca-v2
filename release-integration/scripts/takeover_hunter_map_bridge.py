#!/usr/bin/env python3
"""Convert a reviewed, persisted public.projects export into the Hunter file DTO."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

EXECUTION='IKUN-ONLY-2026-10-16'
TABLES={'public.projects','public.project_workbench','public.project_research','public.project_milestones','public.research_records','public.research_inbox'}
EXPORT_KEYS={'contract','execution_id','package_sha256','snapshot_sha256','mappings'}
ROW_KEYS={'source_system','table','legacy_id','source_sha256','project_id','x_user_id'}
MAX_JSON=16*1024*1024

class BridgeError(ValueError):pass
def require(value,reason):
 if not value:raise BridgeError(reason)
def hash_value(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def private_file(path):
 path=Path(path).absolute();s=path.lstat()
 require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'PRIVATE_REGULAR_INPUT_REQUIRED')
 require(not any(p.is_symlink() for p in path.parents) and stat.S_IMODE(path.parent.stat().st_mode)==0o700,'PRIVATE_INPUT_PARENT_REQUIRED')
 return path
def read_json(path,expected):
 require(hash_value(expected),'INPUT_HASH_REQUIRED');path=private_file(path);require(path.stat().st_size<=MAX_JSON,'JSON_TOO_LARGE');raw=path.read_bytes()
 require(hashlib.sha256(raw).hexdigest()==expected,'INPUT_HASH_MISMATCH')
 def pairs(items):
  result={}
  for key,value in items:require(key not in result,'DUPLICATE_JSON_KEY');result[key]=value
  return result
 def nonfinite(_):raise BridgeError('NONFINITE_JSON')
 value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=nonfinite);require(isinstance(value,dict),'OBJECT_REQUIRED');return value
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
def verify_asset(row):
 require(isinstance(row,dict) and set(row)=={'path','sha256','bytes'} and type(row['bytes']) is int and row['bytes']>=0 and hash_value(row['sha256']),'INVALID_SOURCE_ASSET')
 path=private_file(row['path']);require(path.stat().st_size==row['bytes'] and digest(path)==row['sha256'],'SOURCE_ASSET_DRIFT')
def canonical_id(value):
 require(isinstance(value,str) and value.startswith('prj_'),'INVALID_CANONICAL_ID')
 try:parsed=uuid.UUID(value[4:])
 except (ValueError,AttributeError):raise BridgeError('INVALID_CANONICAL_ID') from None
 require(parsed.version==4 and value=='prj_'+str(parsed),'INVALID_CANONICAL_ID')

def project_maps(export,receipt,manifest,*,package_sha,importer_sha):
 require(set(export)==EXPORT_KEYS and export['contract']=='ikun-projects-takeover-v1' and export['execution_id']==EXECUTION,'UNSUPPORTED_PROJECTS_EXPORT')
 require(hash_value(package_sha) and export['package_sha256']==package_sha and hash_value(importer_sha),'PACKAGE_OR_IMPORTER_HASH_REQUIRED')
 require(manifest.get('contract')=='ikun-takeover-source-manifest-v1' and manifest.get('execution_id')==EXECUTION and manifest.get('scope')=='ikun-main' and manifest.get('status')=='legacy_sources_stopped_final_copies_verified','FINAL_SOURCE_MANIFEST_REQUIRED')
 source=manifest['postgres']['archive'];verify_asset(source);require(export['snapshot_sha256']==source['sha256'],'DUMP_HASH_IS_NOT_MANIFEST_HASH')
 require('dry_run' not in receipt and type(receipt.get('replayed')) is bool and receipt.get('importer_source_sha256')==importer_sha,'PERSISTED_OWNER_RECEIPT_REQUIRED')
 require(all(receipt.get(k)==export[k] for k in EXPORT_KEYS),'OWNER_RECEIPT_EXPORT_MISMATCH')
 rows=export['mappings'];require(isinstance(rows,list) and len(rows)<=20000,'INVALID_MAPPING_ROWS')
 hunter=[];legacy=set();identities=set();unresolved=0;nonprojects=0
 for row in rows:
  require(isinstance(row,dict) and set(row)==ROW_KEYS,'UNSUPPORTED_MAPPING_ROW')
  require(row['source_system']=='ikun-legacy-pg' and row['table'] in TABLES,'UNSUPPORTED_MAPPING_SOURCE')
  require(isinstance(row['legacy_id'],str) and re.fullmatch('[A-Za-z0-9_-]{1,128}',row['legacy_id']) and hash_value(row['source_sha256']),'INVALID_LEGACY_REFERENCE')
  canonical_id(row['project_id']);key=(row['table'],row['legacy_id']);require(key not in legacy,'DUPLICATE_LEGACY_REFERENCE');legacy.add(key)
  if row['table']!='public.projects':nonprojects+=1;continue
  identifier=row['x_user_id']
  if identifier is None:unresolved+=1;continue
  require(isinstance(identifier,str) and re.fullmatch('[0-9]{1,30}',identifier),'INVALID_VERIFIED_X_ID')
  require(identifier not in identities,'AMBIGUOUS_X_MAPPING');identities.add(identifier)
  hunter.append({'x_user_id':identifier,'project_id':row['project_id'],'source_hash':row['source_sha256']})
 return ({'protocol':'hunter-takeover-project-map-v1','execution_id':EXECUTION,'items':sorted(hunter,key=lambda x:x['x_user_id'])},
         {'source_rows':len(rows),'hunter_items':len(hunter),'hunter_unresolved_x':unresolved,'non_project_rows_excluded':nonprojects})

def bridge(*,projects_export,export_sha,projects_receipt,receipt_sha,source_manifest,manifest_sha,package_sha,importer_sha,output):
 export=read_json(projects_export,export_sha);receipt=read_json(projects_receipt,receipt_sha);manifest=read_json(source_manifest,manifest_sha)
 hunter,counts=project_maps(export,receipt,manifest,package_sha=package_sha,importer_sha=importer_sha)
 payloads={'hunter-project-map.json':canonical(hunter)}
 record={'contract':'ikun-hunter-map-bridge-v1','execution_id':EXECUTION,'projects_export_sha256':export_sha,'projects_receipt_sha256':receipt_sha,'projects_package_sha256':package_sha,'projects_importer_sha256':importer_sha,'source_dump_sha256':manifest['postgres']['archive']['sha256'],'source_manifest_sha256':manifest_sha,'converter_sha256':digest(__file__),'counts':counts,'outputs':{name:hashlib.sha256(body).hexdigest() for name,body in payloads.items()},'database_access':False,'new_canonical_ids':0}
 output=Path(output).absolute();require(not any(p.is_symlink() for p in (output,*output.parents)),'OUTPUT_PATH_ALIAS')
 require(output.parent.is_dir() and stat.S_IMODE(output.parent.stat().st_mode)==0o700,'PRIVATE_OUTPUT_PARENT_REQUIRED')
 if output.exists():
  require(output.is_dir() and stat.S_IMODE(output.stat().st_mode)==0o700,'PRIVATE_OUTPUT_DIRECTORY_REQUIRED')
  require({p.name for p in output.iterdir()}==set(payloads)|{'bridge-receipt.json'},'PARTIAL_OR_UNKNOWN_OUTPUT_REQUIRES_REVIEW')
  private_file(output/'bridge-receipt.json');existing=read_json(output/'bridge-receipt.json',digest(output/'bridge-receipt.json'));require(existing==record,'EXISTING_BRIDGE_BINDING_MISMATCH')
  for name,expected in record['outputs'].items():private_file(output/name);require(digest(output/name)==expected,'EXISTING_BRIDGE_OUTPUT_DRIFT')
  return {'state':'REPLAY_NO_ACTION','counts':counts,'receipt_sha256':digest(output/'bridge-receipt.json')}
 output.mkdir(mode=0o700)
 for name,body in {**payloads,'bridge-receipt.json':canonical(record)}.items():
  with os.fdopen(os.open(output/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
 return {'state':'PREPARED_FILE_MAPS_ONLY','counts':counts,'receipt_sha256':digest(output/'bridge-receipt.json')}

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for flag in ('projects-export','export-sha','projects-receipt','receipt-sha','source-manifest','manifest-sha','package-sha','importer-sha','output'):parser.add_argument('--'+flag,required=True)
 args=parser.parse_args()
 try:print(json.dumps(bridge(**vars(args))))
 except (BridgeError,OSError,ValueError,KeyError,TypeError,UnicodeError) as error:parser.exit(2,'MAP_BRIDGE_FAILED: '+(str(error) if isinstance(error,BridgeError) else type(error).__name__)+'\n')

if __name__=='__main__':main()
