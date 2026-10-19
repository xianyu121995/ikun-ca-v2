import test from 'node:test';
import assert from 'node:assert/strict';
import {loadTrackingSubscriptions,invalidateTrackingSubscriptions} from '../../../lib/tracking-subscriptions-cache.ts';
import {readHomeRows,saveHomeRows,significantRowChange,homeRowsKey} from '../../../lib/home-page-size.ts';
const row=n=>({subscription_id:'sub_'+n,project_id:'prj_'+n,x_handle:'account'+n,name:'项目'+n,desired_state:'running'});
test('homepage and voice share an in-flight paginated subscription read; expiry and invalidation refresh it',async()=>{
 const original=globalThis.fetch,clock=Date.now;let now=100_000,calls=0;
 Date.now=()=>now;
 globalThis.fetch=async url=>{calls++;await Promise.resolve();return Response.json({data:{items:[row(String(url).includes('cursor=')?2:1)],next_cursor:String(url).includes('cursor=')?null:'next'}});};
 try{
  const a=loadTrackingSubscriptions('cache-test');const b=loadTrackingSubscriptions('cache-test');assert.equal(a,b);
  const rows=await a;assert.equal(rows.length,2);assert.equal(calls,2);assert.equal((await loadTrackingSubscriptions('cache-test'))[0].x_handle,'account1');assert.equal(calls,2);
  now+=30_001;await loadTrackingSubscriptions('cache-test');assert.equal(calls,4);
  invalidateTrackingSubscriptions('cache-test');await loadTrackingSubscriptions('cache-test');assert.equal(calls,6);
 }finally{globalThis.fetch=original;Date.now=clock;invalidateTrackingSubscriptions('cache-test');}
});
test('subscription cache is isolated by account and failed reads are retryable',async()=>{
 const original=globalThis.fetch;let calls=0;
 globalThis.fetch=async()=>{calls++;return calls===1?new Response('',{status:401}):Response.json({data:{items:[row(calls)],next_cursor:null}});};
 try{
  await assert.rejects(loadTrackingSubscriptions('account-a'));
  assert.equal((await loadTrackingSubscriptions('account-a'))[0].x_handle,'account2');
  assert.equal((await loadTrackingSubscriptions('account-b'))[0].x_handle,'account3');assert.equal(calls,3);
 }finally{globalThis.fetch=original;invalidateTrackingSubscriptions('account-b');}
});
test('row counts survive refresh by height bucket; corrupt/blocked storage is harmless',()=>{
 const data=new Map();const storage={getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v)};
 assert.equal(readHomeRows(storage,820),9);saveHomeRows(storage,820,7);assert.equal(readHomeRows(storage,819),7);assert.equal(readHomeRows(storage,1000),9);
 for(const value of ['0','101','5.2','bad','']){data.set(homeRowsKey(820),value);assert.equal(readHomeRows(storage,820),9);}
 const blocked={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}};assert.equal(readHomeRows(blocked,820),9);assert.doesNotThrow(()=>saveHomeRows(blocked,820,7));
});
test('small row-size changes do not refetch; material layout changes still adapt',()=>{
 assert.equal(significantRowChange(9,8),false);assert.equal(significantRowChange(9,5),true);
 assert.equal(significantRowChange(5,6),false);assert.equal(significantRowChange(5,7),true);
 assert.equal(significantRowChange(30,35),false);assert.equal(significantRowChange(30,38),true);
});
