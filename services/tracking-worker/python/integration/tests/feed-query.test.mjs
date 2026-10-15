import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {join} from 'node:path';
const moduleRoot=fileURLToPath(new URL('../../',import.meta.url));
const {feedQuery}=await import(pathToFileURL(join(moduleRoot,'.b3/preview/apps/website/lib/published-feed.ts')));
const root='http://127.0.0.1/api/v1/tracking/latest?profile=published-v1';
test('Full Unicode query normalization matches the actual Python contract hash',()=>{
 for(const q of [' Straße Σς ',' ＡＢＣ ','İ','\ufb03','100%_literal','\u001c trimmed \u0085']){
  const input=feedQuery(new URL(root+'&q='+encodeURIComponent(q)));
  const expected=execFileSync(join(moduleRoot,'.venv/bin/python'),['-c','import json,sys;from tracking.feed import Query,query_hash;print(query_hash(Query.model_validate(json.loads(sys.stdin.read()))))'],{cwd:moduleRoot,input:JSON.stringify(input.query),encoding:'utf8'}).trim();
  assert.equal(input.hash,expected,q);
 }
});
test('Strict time bounds, profile, duplicates, scope and limit are rejected',()=>{
 for(const suffix of ['&from_at=2026-02-30T00:00:00Z','&from_at=2026-01-01T00:00:00.0001Z','&from_at=0000-01-01T00:00:00Z','&ratings=C','&limit=0','&limit=1.5','&q=a&q=b','&tenant_id=foreign','&actor=admin','&subscription_id=invalid'])assert.throws(()=>feedQuery(new URL(root+suffix)),suffix);
 assert.throws(()=>feedQuery(new URL(root.replace('published-v1','unknown'))));
});
test('Equivalent rating sets and UTC timestamps bind identically while limit stays outside binding',()=>{
 const first=feedQuery(new URL(root+'&ratings=B,S,S&from_at=2026-01-01T00:00:00Z&limit=50'));
 const next=feedQuery(new URL(root+'&ratings=S,B&from_at=2026-01-01T00:00:00.000Z&limit=10'));
 assert.equal(first.hash,next.hash);assert.equal(first.limit,50);assert.equal(next.limit,10);
});

// Private UDS transport fixtures exercise cancellation/concurrency only; business semantics use actual B2 in entries.test.mjs.
const {createServer}=await import('node:http');
const {mkdtempSync,chmodSync,realpathSync,writeFileSync}=await import('node:fs');
const budgetEvidence=[],budgetPath=join(moduleRoot,'artifacts/b3/feed-budgets-'+Date.now()+'.json');function persistBudgets(){writeFileSync(budgetPath,JSON.stringify(budgetEvidence,null,2));writeFileSync(join(moduleRoot,'artifacts/b3/feed-budget-receipt-path.txt'),budgetPath);}persistBudgets();
const {randomUUID}=await import('node:crypto');
const {publishedFeed}=await import(pathToFileURL(join(moduleRoot,'.b3/preview/apps/website/lib/published-feed.ts')));
async function budgetFixture(mode){
 const folder=realpathSync(mkdtempSync('/private/tmp/ik-b3-budget-'));chmodSync(folder,0o700);const socket=join(folder,'rpc.sock');
 const previous={};for(const key of ['IKUN_PROJECTS_IPC_SOCKET','IKUN_PROJECTS_IPC_TOKEN','IKUN_PROJECTS_BUILD_SHA'])previous[key]=process.env[key];
 Object.assign(process.env,{IKUN_PROJECTS_IPC_SOCKET:socket,IKUN_PROJECTS_IPC_TOKEN:'synthetic-budget-token-xxxxxxxxxxxxxxxx',IKUN_PROJECTS_BUILD_SHA:'a'.repeat(40)});
 const ids=Array.from({length:mode==='whole'?1601:601},()=> 'prj_'+randomUUID());let attempt=0,active=0,maxActive=0,aborted=0;let markHanging;const hangingStarted=new Promise(resolve=>markHanging=resolve);
 const server=createServer(async(req,res)=>{let body='';try{for await(const chunk of req)body+=chunk;}catch{return;}const payload=JSON.parse(body);active++;maxActive=Math.max(maxActive,active);let finished=false,timer;const release=()=>{if(!finished){finished=true;active--;clearTimeout(timer);}};res.once('close',release);res.once('finish',release);
  const projectIds=payload.body.project_ids;
  if(mode==='retry'&&attempt===1&&projectIds.includes(ids[200])){await hangingStarted;res.writeHead(409,{'content-type':'application/json'});res.end(JSON.stringify({error:{code:'VERSION_CONFLICT'},request_id:payload.request_id}));return;}
  if(mode==='timeout'||mode==='retry'&&attempt===1&&projectIds.includes(ids[400])){res.once('close',()=>aborted++);markHanging();return;}
  const send=()=>{if(res.destroyed)return;res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({data:{contract:'tracking-ratings-v1',catalog_version:'v'+attempt,checked_at:new Date().toISOString(),items:projectIds.map(project_id=>({project_id,state:'found',rating:'A',revision:1}))},request_id:payload.request_id}));};
  if(mode==='whole')timer=setTimeout(send,1300);else send();
 });
 await new Promise(r=>server.listen(socket,r));chmodSync(socket,0o600);
 const request=new Request(root),input=feedQuery(new URL(root));
 async function service(path,id,options={}){
  if(mode==='whole'&&path==='feed/bases')await new Promise((resolve,reject)=>{const timer=setTimeout(resolve,1900);options.signal.addEventListener('abort',()=>{clearTimeout(timer);reject(Error('ABORTED'));},{once:true});});
  if(options.signal?.aborted)throw Error('ABORTED');
  let data;
  if(path==='feed/bases'){attempt++;data={basis_id:'fbs_'+randomUUID(),query_hash:input.hash,semantic_revision:1,project_ids:ids};}
  else if(path==='feed/snapshots')data={snapshot:{ratings_catalog_version:'v'+attempt},items:[],matched_total:0,next_cursor:null};
  else if(path==='status')data={semantic_revision:1};else throw Error(path);
  return Response.json({data,request_id:id});
 }
 try{const start=Date.now(),response=await publishedFeed(request,{user_id:'usr_budget',tenant_id:'ikun-main',role:'user'},'req_budget',service);await new Promise(r=>setTimeout(r,20));const duration=Date.now()-start;budgetEvidence.push({mode,status:response.status,duration_ms:duration,attempts:attempt,max_active:maxActive,active_after_cancel:active,hanging_aborted:aborted});persistBudgets();return{response,duration,attempts:attempt,maxActive,active,aborted};}
 finally{server.closeAllConnections();await new Promise(r=>server.close(r));for(const[key,value]of Object.entries(previous)){if(value===undefined)delete process.env[key];else process.env[key]=value;}}
}
test('Retry cancels and drains a conflicting pair before starting the next attempt',async()=>{const result=await budgetFixture('retry');assert.equal(result.response.status,200);assert.equal(result.attempts,2);assert.ok(result.maxActive<=2,JSON.stringify(result));assert.equal(result.active,0);assert.equal(result.aborted,1);});
test('One hung ratings request cancels at the two-second lookup budget without partial data',async()=>{const result=await budgetFixture('timeout');assert.equal(result.response.status,503);const body=await result.response.json();assert.equal(body.data,undefined);assert.ok(result.duration>=1700&&result.duration<3500);assert.equal(result.active,0);});
test('The entire feed cancels at eight seconds even when each ratings batch stays below two',async()=>{const result=await budgetFixture('whole');assert.equal(result.response.status,503);assert.equal((await result.response.json()).data,undefined);assert.ok(result.duration>=7500&&result.duration<9500);assert.ok(result.maxActive<=2);assert.equal(result.active,0);});

test('Worker query failures preserve explicit errors while dropping upstream transport framing',async()=>{
 const response=await publishedFeed(new Request(root),{user_id:'usr_proxy',tenant_id:'ikun-main',role:'user'},'req_proxy',async()=>new Response(JSON.stringify({error:{code:'RATE_LIMITED',message:'capacity',retryable:true},request_id:'req_proxy'}),{status:429,headers:{'content-type':'application/json','content-length':'99999','connection':'keep-alive','retry-after':'1'}}));
 assert.equal(response.status,429);assert.equal(response.headers.get('retry-after'),'1');assert.equal(response.headers.has('content-length'),false);assert.equal(response.headers.has('connection'),false);assert.equal((await response.json()).error.code,'RATE_LIMITED');
});

test('Malformed query view hints are rejected before any resource request',async()=>{
 for(const value of ['','qv1_NOT_A_UUID','qv1_550E8400-e29b-41d4-a716-446655440001','qv1_550e8400-e29b-41d4-a716-446655440001,qv1_550e8400-e29b-41d4-a716-446655440001']){
  let calls=0;const response=await publishedFeed(new Request(root,{headers:{'x-tracking-query-view':value}}),{user_id:'usr_view',tenant_id:'ikun-main',role:'user'},'req_view',async()=>{calls++;throw Error('MUST_NOT_CALL');});assert.equal(response.status,422);assert.equal(calls,0);
 }
});
