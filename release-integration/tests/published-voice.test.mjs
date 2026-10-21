import test from 'node:test';
import assert from 'node:assert/strict';
import {PublishedVoiceFeed} from '../../apps/website/lib/published-voice-feed.ts';
import {bindVoiceOwner} from '../../apps/website/lib/voice-browser-owner.ts';
const uuid=n=>`00000000-0000-4000-8000-${n.toString(16).padStart(12,'0')}`;
const at=Date.parse('2026-10-22T04:00:00Z');
const row=(n,patch={})=>({activity_id:'act_'+uuid(n),subscription_id:'sub_'+uuid(1),project_id:'prj_'+uuid(1),name:'中文项目',rating:'A',occurred_at:new Date(at-1000).toISOString(),...patch});
const response=items=>Response.json({data:{profile:'published-v1',items,next_cursor:null},request_id:'fixture'},{headers:{'x-ikun-server-time':new Date(at).toISOString()}});
function setup(){let items=[],requests=0,revoked=false;const calls=[],connections=[];const feed=new PublishedVoiceFeed({request:async(_path,init)=>{assert.equal(init.credentials,'same-origin');requests++;return response(items);},onItem:r=>calls.push(r),connected:r=>connections.push(r),revoke:()=>{revoked=true;}});return {feed,calls,connections,set:x=>{items=x;},requests:()=>requests,revoked:()=>revoked};}
test('initial list is silent; new WSS, REST and unknown published rows speak once',async()=>{const s=setup();s.set([row(1)]);await s.feed.refresh();assert.equal(s.calls.length,0);s.set([row(4,{source:'rest',tweet_kind:'unknown',replay:true}),row(3,{source:'rest'}),row(2,{source:'wss'}),row(1)]);await s.feed.refresh();assert.deepEqual(s.calls.map(x=>x.activity_id),[2,3,4].map(n=>'act_'+uuid(n)));await s.feed.refresh();assert.equal(s.calls.length,3);s.feed.stop();});
test('only server time governs ten-minute eligibility, not a skewed client clock',async()=>{const original=Date.now;for(const skew of [-1000,60000,-600000]){Date.now=()=>at+skew;const s=setup();await s.feed.refresh();s.set([row(2),row(3,{occurred_at:new Date(at-600001).toISOString()}),row(4,{occurred_at:null}),row(5,{occurred_at:new Date(at+1000).toISOString()})]);await s.feed.refresh();assert.deepEqual(s.calls.map(x=>x.activity_id),['act_'+uuid(2)]);s.feed.stop();}Date.now=original;});
test('concurrent refreshes coalesce and an SSE during flight triggers an immediate trailing read',async()=>{let release,count=0;const feed=new PublishedVoiceFeed({request:async()=>{count++;if(count===1)await new Promise(r=>release=r);return response([]);},onItem(){},connected(){},revoke(){}});const pending=feed.refresh();feed.refresh();feed.refresh();assert.equal(count,1);release();await pending;await new Promise(r=>setImmediate(r));assert.equal(count,2);feed.stop();});
test('401 revokes and stops polling without consuming a list',async()=>{let count=0,revoked=0;const feed=new PublishedVoiceFeed({request:async()=>{count++;return new Response('',{status:401});},onItem(){throw Error('must not speak');},connected(){},revoke(){revoked++;}});await feed.refresh();await feed.refresh();assert.equal(count,1);assert.equal(revoked,1);});
test('a failed first read does not turn the existing initial list into new items',async()=>{let count=0;const calls=[];const feed=new PublishedVoiceFeed({request:async()=>++count===1?new Response('',{status:503}):response([row(1)]),onItem:r=>calls.push(r),connected(){},revoke(){}});await feed.refresh();await feed.refresh();assert.equal(calls.length,0);feed.stop();});
test('two eligible tabs share an exclusive speaker and persistent activity claims across handoff',async()=>{
 const locks=new Map(),storage=new Map();
 const target={localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)},navigator:{locks:{async request(name,options,callback){while(locks.has(name)){await locks.get(name);if(options.signal.aborted)return;}if(options.signal.aborted)return;let done;locks.set(name,new Promise(r=>done=r));try{await callback();}finally{locks.delete(name);done();}}}}};
 const controller=()=>({getSnapshot:()=>({enabled:true,armed:true,connected:true,available:'available',status:'ready'}),subscribe:()=>()=>{}});
 const a=bindVoiceOwner(controller(),target),b=bindVoiceOwner(controller(),target);await new Promise(r=>setImmediate(r));assert.equal(a.isLeader(),true);assert.equal(b.isLeader(),false);
 let spoken=0;assert.equal(a.claim('user','activity',at,()=>{spoken++;return true;}),true);assert.equal(b.claim('user','activity',at,()=>{spoken++;return true;}),false);
 a.dispose();await new Promise(r=>setImmediate(r));assert.equal(b.isLeader(),true);assert.equal(b.claim('user','activity',at+1000,()=>{spoken++;return true;}),false);assert.equal(spoken,1);b.dispose();
});
test('published-v1 responses carry a fresh server clock without changing the feed DTO',async()=>{
 const {publishedFeed,feedQuery}=await import('../../apps/website/lib/published-feed.ts');
 const url=new URL('http://fixture/api/v1/tracking/latest?profile=published-v1&limit=100');const input=feedQuery(url);
 const page={profile:'published-v1',items:[],next_cursor:null,snapshot:{ratings_catalog_version:null}};
 const service=async path=>Response.json({data:path==='feed/bases'?{query_hash:input.hash,project_ids:[],basis_id:'fixture',semantic_revision:1}:path==='status'?{semantic_revision:1}:page,request_id:'fixture'});
 const response=await publishedFeed(new Request(url),{user_id:'fixture-user',role:'user',tenant_id:'ikun-main'},'fixture',service);
 assert.equal(response.status,200);assert.ok(Math.abs(Date.parse(response.headers.get('x-ikun-server-time'))-Date.now())<1000);assert.deepEqual((await response.json()).data,page);
});
