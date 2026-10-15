import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveCommand} from '../../apps/website/lib/service-gateway/commands.ts';
const command='cmd_11111111-1111-4111-8111-111111111111',project='prj_22222222-2222-4222-8222-222222222222';
const id='gateway_fixture';
const data=(overrides={})=>({command_id:command,state:'pending',project_id:project,subscription_id:null,revision:null,updated_at:'2026-10-16T01:00:00+00:00',error_code:null,request_id:id,...overrides});
const ok=(value)=>Response.json({data:value,request_id:id});
const error=(status,code)=>Response.json({error:{code,message:'synthetic source error',retryable:status===503},request_id:id},{status});
const missing=()=>error(404,'NOT_FOUND');
const down=()=>error(503,'UPSTREAM_UNAVAILABLE');
function lookups(overrides={}){return {projects:async()=>missing(),hunter:async()=>missing(),tracking:async()=>missing(),canonical:async()=>ok({project_id:project}),...overrides};}
test('old running or succeeded is not current truth when Tracking proves absence',async()=>{
 for(const state of ['running','succeeded','failed','accepted']){
  const result=await resolveCommand(command,id,lookups({projects:async()=>ok(data({state}))}));
  assert.equal(result.status,503,state);assert.ok(!(await result.json()).data);
 }
});
test('Projects pending and unknown stay honest while command is not delivered',async()=>{
 for(const state of ['pending','unknown']){const result=await resolveCommand(command,id,lookups({projects:async()=>ok(data({state}))}));assert.equal((await result.json()).data.state,state);}
});
test('Projects unavailable is retained and does not become an owner fallback',async()=>{
 let called=0;const fail=async()=>{called++;return ok(data({state:'running'}));};
 const result=await resolveCommand(command,id,lookups({projects:async()=>down(),hunter:fail,tracking:fail}));
 assert.equal(result.status,503);assert.equal(called,0);
});
test('wrong Projects envelope blocks without leaking payload or probing owners',async()=>{
 let called=0;const bad=Response.json({data:data(),request_id:'wrong',secret:'synthetic-do-not-leak'});
 const result=await resolveCommand(command,id,lookups({projects:async()=>bad,hunter:async()=>{called++;return missing();}}));
 assert.equal(result.status,503);assert.equal(called,0);assert.ok(!(await result.text()).includes('do-not-leak'));
});
test('legal direct Tracking is readable while unrelated Hunter is unavailable',async()=>{
 const result=await resolveCommand(command,id,lookups({hunter:async()=>down(),tracking:async()=>ok(data({state:'running',subscription_id:'sub_33333333-3333-4333-8333-333333333333',revision:1}))}));
 assert.equal(result.status,200);assert.equal((await result.json()).data.state,'running');
});
test('verified direct Tracking does not wait for an unrelated hung Hunter',async()=>{
 const result=await Promise.race([resolveCommand(command,id,lookups({hunter:()=>new Promise(()=>{}),tracking:async()=>ok(data())})),new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('unrelated source blocked response')),1000);timer.unref();})]);
 assert.equal(result.status,200);
});
test('all three confirmed NOT_FOUND remain NOT_FOUND',async()=>{assert.equal((await resolveCommand(command,id,lookups())).status,404);});
test('an unavailable source is never changed into all-sources NOT_FOUND',async()=>{assert.equal((await resolveCommand(command,id,lookups({hunter:async()=>down()}))).status,503);});
test('unmapped Hunter preserves original nullable pending projection',async()=>{
 const result=await resolveCommand(command,id,lookups({hunter:async()=>ok(data({project_id:null})),tracking:async()=>down()}));
 assert.equal(result.status,200);const value=(await result.json()).data;assert.equal(value.command_id,command);assert.equal(value.project_id,null);
});
test('complete CommandResultV2 rejects missing, extra, malformed and mismatched fields',async()=>{
 const mutations=[x=>{delete x.revision;},x=>{x.extra='synthetic-do-not-leak';},x=>{x.command_id=command.replace('11111111','99999999');},
  x=>{x.project_id='prj_00000000-0000-0000-0000-000000000000';},x=>{x.subscription_id='sub_bad';},x=>{x.revision=0;},x=>{x.revision=true;},
  x=>{x.updated_at='2026-02-30T01:00:00Z';},x=>{x.updated_at='2026-10-16T01:00:00';},x=>{x.error_code={secret:'bad'};},x=>{x.request_id='wrong';}];
 for(const mutate of mutations){const row=data();mutate(row);const result=await resolveCommand(command,id,lookups({projects:async()=>ok(row)}));assert.equal(result.status,503);assert.ok(!(await result.text()).includes('do-not-leak'));}
});
test('Tracking projection must match Projects canonical and full transport contract',async()=>{
 for(const row of [data({project_id:'prj_99999999-9999-4999-8999-999999999999'}),{...data(),raw:'synthetic-do-not-leak'}]){
  const result=await resolveCommand(command,id,lookups({projects:async()=>ok(data()),tracking:async()=>ok(row)}));assert.equal(result.status,503);assert.ok(!(await result.text()).includes('do-not-leak'));
 }
});
test('direct Tracking canonical must be verified in Projects scope',async()=>{
 const result=await resolveCommand(command,id,lookups({tracking:async()=>ok(data()),canonical:async()=>ok({project_id:'wrong'})}));assert.equal(result.status,503);
});
