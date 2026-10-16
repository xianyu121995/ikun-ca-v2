"""Pure fixtures; no provider, process or runtime database access."""
import copy
import asyncio
import json
import httpx
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sample_readonly_preflight as m


class ReadonlyPreflight(unittest.TestCase):
 def setUp(self):
  self.profile={'success':True,'data':{'userId':'123456789','screenName':'0x2a_ikun','followersCount':123}}
  self.row={'id':'owned-1','twAccount':'fixture_legacy','groupName':'original-fixture-group','newTweetBol':True,'newTweetQuoteBol':False}
  self.ownership={'owned':[{'watch_id':'owned-1','x_handle':'fixture_legacy','flags':{'newTweetBol':True,'newTweetQuoteBol':False},'groups':{'groupName':'original-fixture-group'}}],'excluded_handles':['fictional_alpha'],'excluded_watch_ids':['alpha-1'],'excluded_x_user_ids':['98765']}
 def check(self,rows,body=None):
  normalized={r['twAccount']:r for r in rows};used=sum(r['newTweetBol']for r in rows);capacity={'new_tweet_used':used,'new_tweet_limit':600,'available':max(0,600-used)}
  return m.watch_result(body or {'success':True,'data':rows},normalized,capacity,self.ownership,m.identity(self.profile))
 def test_profile_stable_identity_and_actual_5000_boundary(self):
  self.assertEqual(m.identity(self.profile)['hunter_mode'],'REST');self.profile['data']['followersCount']=5000;self.assertEqual(m.identity(self.profile)['hunter_mode'],'WSS')
 def test_guessed_id_or_boolean_count_rejected(self):
  self.profile['data']['userId']=123
  with self.assertRaises(m.SafeFailure):m.identity(self.profile)
  self.profile['data']['userId']='123';self.profile['data']['followersCount']=True
  with self.assertRaises(m.SafeFailure):m.identity(self.profile)
 def test_full_list_and_explicit_total_preserve_all_flags(self):
  before=copy.deepcopy(self.row);result=self.check([self.row],{'success':True,'data':{'list':[self.row],'total':1,'usage':{'cost':'ignored','quota':'ignored'}}});self.assertTrue(result['new_slot_possible']);self.assertEqual(result['legacy_ownership_anchors_matched'],1);self.assertEqual(self.row,before)
 def test_observed_top_total_envelope_and_nested_total_are_exact(self):
  result=self.check([self.row],{'success':True,'data':[self.row],'total':1,'usage':{'cost':'ignored','quota':'ignored'}});self.assertEqual(result['watch_total'],1)
  for total in (True,0,2,None):
   with self.subTest(total=total):
    with self.assertRaises(m.SafeFailure):self.check([self.row],{'success':True,'data':[self.row],'total':total})
  with self.assertRaises(m.SafeFailure):self.check([self.row],{'success':True,'data':{'list':[self.row],'total':1},'total':2})
 def test_pagination_or_missing_total_never_claims_full_snapshot(self):
  for payload in ({'success':True,'data':[self.row],'has_more':True},{'success':True,'data':{'list':[self.row]}},{'success':True,'data':{'list':[self.row],'total':2}}):
   with self.subTest(payload=payload):
    with self.assertRaises(m.SafeFailure):self.check([self.row],payload)
 def test_wrong_account_ownership_anchor_stops(self):
  row={**self.row,'id':'other-account-id'}
  with self.assertRaisesRegex(m.SafeFailure,'OWNERSHIP_ANCHOR'):self.check([row])
 def test_existing_target_unowned_is_reported_never_mutated(self):
  row={**self.row,'id':'new-target-id','twAccount':m.TARGET};result=self.check([self.row,row]);self.assertEqual(result['test_watch_ownership'],'existing_ownership_unproven_do_not_touch');self.assertFalse(result['new_slot_possible']);self.assertFalse(result['current_watch_mutation_allowed'])
 def test_full_600_counts_all_rows_even_unknown_owner(self):
  rows=[self.row]+[{**self.row,'id':str(i),'twAccount':'fixture_'+str(i)}for i in range(599)];result=self.check(rows);self.assertEqual(result['new_tweet_used'],600);self.assertFalse(result['new_slot_possible'])
 def test_excluded_renamed_alpha_watch_is_rejected(self):
  with self.assertRaisesRegex(m.SafeFailure,'ALPHA_OR_EXCLUDED'):self.check([self.row,{**self.row,'id':'alpha-1','twAccount':m.TARGET}])
 def run_mock_transport(self,first_status=200,field='OPENNEWS_TOKEN'):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as root:
   directory=Path(root);directory.chmod(0o700);credential=directory/'fixture.env';credential.write_text(field+'=fixture-not-a-real-provider-credential-000000\n');credential.chmod(0o600);ownership=directory/'ownership.json';m.atomic(ownership,self.ownership)
   tracking=m.ops.V2/'releases'/m.ops.SOURCE/'services/tracking-worker/python';hunter=m.ops.V2/'releases/f9e3c6cbf7c44676c37ef973389e6176777640ce/services/hunter-worker/python';plan={'tracking_python_root':str(tracking),'hunter_python_root':str(hunter),'credential_source':str(credential),'credential_field':field,'peer_plan':{},'ownership':{'path':str(ownership)}};calls=[]
   def handler(request):
    calls.append((request.url.path,json.loads(request.content)))
    if request.url.path.endswith('twitter_user_info'):return httpx.Response(first_status,json=self.profile if first_status==200 else {'success':False,'message':'synthetic rate limit'})
    self.assertEqual(request.url.path,'/open/twitter_watch');return httpx.Response(200,json={'success':True,'data':[self.row],'total':1,'usage':{'cost':'ignored','quota':'ignored'}})
   with patch.object(httpx,'AsyncHTTPTransport',return_value=httpx.MockTransport(handler)),patch.object(m.ops,'peers',return_value={'alpha':{'reconnects':3}}),patch.object(m.ops.TrackingOps,'ready'),patch('sqlite3.connect',side_effect=AssertionError('no runtime DB in preflight')):
    if first_status==200:
     value=asyncio.run(m.run(plan,directory));self.assertEqual(value['provider_attempts'],2);self.assertEqual([x[1]for x in calls],[{'username':m.TARGET},{}]);self.assertEqual(m.read_json(directory/'result.private.json')['watch']['legacy_ownership_anchors_matched'],1)
    else:
     with self.assertRaises(Exception):asyncio.run(m.run(plan,directory))
     self.assertEqual(m.read_json(directory/'failure.private.json')['provider_attempts'],1)
   return calls
 def test_original_remote_uses_two_raw_reads_with_top_total_no_database(self):
  self.assertEqual(len(self.run_mock_transport()),2)
 def test_existing_hunter_alias_drives_only_6551_client(self):
  self.assertEqual(len(self.run_mock_transport(field='TWITTER_API_TOKEN')),2)
 def test_rest_key_is_not_an_approved_6551_alias(self):
  with self.assertRaisesRegex(m.SafeFailure,'6551_CREDENTIAL_FIELD_NOT_APPROVED'):m.credential_field({'credential_field':'TWITTERAPI_IO_API_KEY'})
 def test_429_consumes_one_attempt_and_never_retries_or_reads_watch(self):
  self.assertEqual(len(self.run_mock_transport(429)),1)
 def test_credentials_check_never_reads_values(self):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as root:
   p=Path(root)/'fixture.env';p.write_text('SYNTHETIC_ONLY=not-a-credential\n');p.chmod(0o600)
   with patch.object(Path,'read_text',side_effect=AssertionError('no secret read in dry-run')):
    result=m.credentials_presence(p);self.assertTrue(result['file_exists']);self.assertTrue(result['private_regular_owned']);self.assertFalse(result['values_read'])


if __name__=='__main__':unittest.main()
