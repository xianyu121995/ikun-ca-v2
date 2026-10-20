import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture,req} from '../../modules/auth/tests/helpers.mjs';
import {hunterEventsRoute} from '../../apps/website/lib/hunter.ts';
test('replayed Hunter events revalidate identity without 50 synchronous session writes',async()=>{
 const oldFetch=globalThis.fetch,oldURL=process.env.HUNTER_API_URL,oldToken=process.env.HUNTER_API_TOKEN;
 Object.assign(process.env,{HUNTER_API_URL:'http://127.0.0.1:4011',HUNTER_API_TOKEN:'h'.repeat(64)});
 let read=0;globalThis.fetch=async()=>Response.json({data:{items:read++===0?Array.from({length:50},(_,n)=>({sequence:n+1,type:'hunter.discovery.updated',data:{discovery_id:'fixture-'+n,revision:1}})):[]},request_id:'fixture'});
 try{await fixture(async e=>{const old=globalThis.ikunAuth;globalThis.ikunAuth=e.api;const touches=[],original=e.store.authenticate.bind(e.store);e.store.authenticate=(token,touch)=>{touches.push(touch===true);return original(token,touch);};
  try{const request=req('/api/v1/hunter/events','GET',undefined,e.root,{'x-request-id':'fixture'});const response=await hunterEventsRoute(request),reader=response.body.getReader();const part=await reader.read();assert.equal(response.status,200);assert.equal(new TextDecoder().decode(part.value).match(/event: hunter.discovery.updated/g).length,50);await reader.cancel();assert.ok(touches.filter(Boolean).length<=3);assert.ok(touches.filter(v=>!v).length>=50);}
  finally{globalThis.ikunAuth=old;}
 });}finally{globalThis.fetch=oldFetch;if(oldURL===undefined)delete process.env.HUNTER_API_URL;else process.env.HUNTER_API_URL=oldURL;if(oldToken===undefined)delete process.env.HUNTER_API_TOKEN;else process.env.HUNTER_API_TOKEN=oldToken;}
});
