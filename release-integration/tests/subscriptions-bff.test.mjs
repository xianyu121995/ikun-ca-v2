import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {chmodSync,mkdtempSync,rmSync} from 'node:fs';
import {fixture,req} from '../../modules/auth/tests/helpers.mjs';
import {trackingRoute} from '../../apps/website/lib/tracking.ts';
test('complete subscriptions use bounded parallel rating batches, timing headers, and fail closed',async()=>{
 const directory=mkdtempSync('/private/tmp/ikun-speed-ratings-'),socket=directory+'/p.sock';chmodSync(directory,0o700);
 const names=['IKUN_PROJECTS_IPC_SOCKET','IKUN_PROJECTS_IPC_TOKEN','IKUN_PROJECTS_BUILD_SHA','TRACKING_API_URL','TRACKING_API_TOKEN'],before=names.map(k=>process.env[k]);
 Object.assign(process.env,{IKUN_PROJECTS_IPC_SOCKET:socket,IKUN_PROJECTS_IPC_TOKEN:'r'.repeat(64),IKUN_PROJECTS_BUILD_SHA:'f'.repeat(40),TRACKING_API_URL:'http://127.0.0.1:4012',TRACKING_API_TOKEN:'t'.repeat(64)});
 let mode='ok',active=0,peak=0,batches=[];
 const server=http.createServer(async(request,response)=>{
  let body='';for await(const chunk of request)body+=chunk;
  const value=JSON.parse(body),ids=value.body.project_ids;assert.ok(ids.length<=200);batches.push(ids.length);active++;peak=Math.max(peak,active);await new Promise(r=>setTimeout(r,30));active--;
  const failed=mode==='fail'&&ids.length===50;response.writeHead(failed?503:200,{'content-type':'application/json'});
  response.end(JSON.stringify(failed?{error:{code:'UPSTREAM_UNAVAILABLE',message:'mock failure'},request_id:value.request_id}:{data:{contract:'tracking-ratings-v1',catalog_version:mode==='changed'&&ids.length===50?'new-version':'fixture',checked_at:new Date().toISOString(),items:ids.map(project_id=>({project_id,state:'found',rating:'A',revision:1}))},request_id:value.request_id}));
 });
 await new Promise(r=>server.listen(socket,r));chmodSync(socket,0o600);
 const oldFetch=globalThis.fetch;globalThis.fetch=async()=>Response.json({data:{items:Array.from({length:450},(_,n)=>({project_id:`prj_550e8400-e29b-41d4-a716-${String(n).padStart(12,'0')}`,subscription_id:'sub_'+n,rating:null})),next_cursor:null},request_id:'fixture'});
 try{await fixture(async e=>{const old=globalThis.ikunAuth;globalThis.ikunAuth=e.api;try{
  for(const next of ['ok','fail','changed']){
   mode=next;batches=[];peak=0;const response=await trackingRoute(req('/api/v1/tracking/subscriptions?limit=1000&include_removed=true','GET',undefined,e.root));
   assert.deepEqual(batches.sort((a,b)=>a-b),[50,200,200]);assert.equal(peak,3);
   const value=await response.json();
   if(next==='ok'){assert.equal(response.status,200);assert.equal(value.data.items.length,450);assert.ok(value.data.items.every(row=>row.rating==='A'));assert.match(response.headers.get('server-timing'),/total;dur=/);}
   else {assert.equal(response.status,next==='fail'?503:409);assert.equal('data'in value,false);}
  }
 }finally{globalThis.ikunAuth=old;}});
 }finally{globalThis.fetch=oldFetch;server.closeAllConnections();await new Promise(r=>server.close(r));rmSync(directory,{recursive:true,force:true});names.forEach((k,i)=>{if(before[i]===undefined)delete process.env[k];else process.env[k]=before[i];});}
});
