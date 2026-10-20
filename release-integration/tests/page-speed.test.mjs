import test from 'node:test';
import assert from 'node:assert/strict';
import {clearClientSession,peekClientData,saveClientData,readClientData,invalidateClientData,keyedRefresh} from '../../apps/website/lib/client-session-cache.ts';
test('memory cache displays last data while refresh runs; simultaneous consumers share one request',async()=>{
 clearClientSession();saveClientData('alice','page',{revision:1});let resolve,calls=0;
 const load=()=>{calls++;return new Promise(r=>resolve=r);};
 const a=readClientData('alice','page',load),b=readClientData('alice','page',load);assert.equal(a,b);assert.deepEqual(peekClientData('alice','page'),{revision:1});
 await Promise.resolve();assert.equal(calls,1);resolve({revision:2});await a;assert.deepEqual(peekClientData('alice','page'),{revision:2});
});
test('logout and account switch fence in-flight responses; old data cannot repopulate cache',async()=>{
 clearClientSession();let resolve;const a=readClientData('alice','page',()=>new Promise(r=>resolve=r));await Promise.resolve();
 saveClientData('bob','page','bob-only');resolve('alice-private');await a;assert.equal(peekClientData('bob','page'),'bob-only');assert.equal(peekClientData('alice','page'),undefined);
 let end;const old=readClientData('alice','page',()=>new Promise(r=>end=r));await Promise.resolve();clearClientSession();end('old');await old;assert.equal(peekClientData('alice','page'),undefined);
});
test('mutations invalidate snapshots and reads; failures retry without stale promise poisoning',async()=>{
 clearClientSession();saveClientData('alice','page',1);invalidateClientData('alice','page');assert.equal(peekClientData('alice','page'),undefined);
 await assert.rejects(readClientData('alice','page',async()=>{throw Error('offline');}));assert.equal(await readClientData('alice','page',async()=>2),2);
});
test('mount, polling and SSE dedupe; a changed filter queues exactly one fresh view',async()=>{
 let key='first',calls=0,resolve;const refresh=keyedRefresh(async()=>{calls++;await new Promise(r=>resolve=r);},()=>key);
 const a=refresh();await Promise.resolve();const b=refresh();assert.equal(a,b);key='second';const c=refresh(),d=refresh();resolve();await a;await new Promise(r=>setTimeout(r,0));assert.equal(calls,2);resolve();await Promise.all([c,d]);assert.equal(calls,2);
});
