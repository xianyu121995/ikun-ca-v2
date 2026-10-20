/** All API responses are synthetic. No production sessions, providers, Watch or real audio. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
const require=createRequire(import.meta.url),{build}=require('../../packages/ui/node_modules/esbuild'),{chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=fileURLToPath(new URL('../../',import.meta.url)),uid='usr_00000000-0000-4000-8000-000000000001',pid='prj_779afd82-bc46-4293-9735-1b47863fc7a5',sid='sub_d4bf0a2e-00dc-49f8-bbf3-a1231bcb7475';
const bundle=await build({stdin:{contents:`import React,{useState} from 'react';import {createRoot} from 'react-dom/client';import {VoiceDock} from './components/voice-dock';import Hunter from './components/hunter-controller';import {TrackingLive} from './components/tracking-live';import Home from './components/projects-home';
const session={user_id:'${uid}',username:'fixture',role:'superadmin',csrf_token:'fixture-csrf',must_change_password:false,capabilities:{can_manage_hunter:true}};
function App(){const [page,setPage]=useState('home');return <VoiceDock><nav style={{position:'fixed',top:0,left:400,zIndex:99999}}>{['home','hunter','tracking'].map(p=><button id={'go-'+p} onClick={()=>setPage(p)} key={p}>{p}</button>)}</nav>{page==='home'?<Home userId={session.user_id} csrf={session.csrf_token} context={{mode:'live',role:'superadmin',capabilities:{can_edit_projects:true}}}/>:page==='hunter'?<Hunter session={session}/>:<TrackingLive csrf={session.csrf_token} canManage username="fixture" voiceSession={{user_id:session.user_id,role:'superadmin',epoch:'fixture'}}/>}</VoiceDock>}createRoot(document.getElementById('root')).render(<App/>);`,resolveDir:root+'apps/website',loader:'tsx'},bundle:true,write:false,outdir:'/private/tmp/ikun-speed-browser-bundle',format:'iife',jsx:'automatic',define:{'process.env.NODE_ENV':'"production"'}});
const project={project_id:pid,name:'性能测试项目',rating:'A',description:'仅用于 mock 的项目简介',notes:'mock',category:'新协议',progress_stage:'researching',progress_percent:null,website_url:null,token_date:null,token_date_status:'unconfirmed',home_membership:'active',revision:7,discovered_at:'2026-10-20T00:00:00.000Z',created_at:'2026-10-20T00:00:00.000Z',updated_at:'2026-10-20T00:00:00.000Z'};
const home={project,milestone:{date:null,hour:null,title:'',status:'unconfirmed'},completion:null};
const sub={subscription_id:sid,project_id:pid,name:project.name,x_handle:'fixture_only',notes:'mock',revision:7,desired_state:'running',observed_state:'running',operation_state:'succeeded',connection:'connected',rating:'A'};
const discovery={discovery_id:'disc_fixture',project_id:pid,project:{...project},x_handle:'fixture_only',profile_bio:'mock',signal_count:2,review_state:'tracking',monitoring_state:'succeeded',revision:7,discovered_at:project.discovered_at,last_seen_at:project.updated_at};
const streams=new Set(),requests=[];let delay=220;
const server=createServer(async(req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname==='/app.js'){res.setHeader('content-type','text/javascript');res.end(bundle.outputFiles.find(f=>f.path.endsWith('.js'))?.contents??bundle.outputFiles[0].contents);return;}
 if(url.pathname==='/app.css'){res.setHeader('content-type','text/css');res.end(bundle.outputFiles.find(f=>f.path.endsWith('.css'))?.contents??'');return;}
 if(url.pathname==='/api/v1/tracking/events'||url.pathname==='/api/v1/hunter/events'){
  requests.push({path:req.url,method:'SSE',at:Date.now()});streams.add(res);res.writeHead(200,{'content-type':'text/event-stream'});res.write(': heartbeat\n\n');res.on('close',()=>streams.delete(res));
  if(url.pathname.endsWith('/hunter/events'))res.write(`event: hunter.discovery.updated\ndata: ${JSON.stringify({data:discovery,request_id:'fixture'})}\n\n`);return;
 }
 if(url.pathname.startsWith('/api/')){
  requests.push({path:req.url,method:req.method,at:Date.now(),headers:req.headers});let data;
  if(url.pathname==='/api/v1/auth/me')data={user_id:uid,role:'superadmin',must_change_password:false};
  else if(url.pathname==='/api/v1/system/health')data={healthy:true,errors:[]};
  else if(url.pathname==='/api/v1/tracking/subscriptions')data={items:[sub],next_cursor:null};
  else if(url.pathname==='/api/v1/hunter/signals')data={items:[discovery],next_cursor:null};
  else if(url.pathname==='/api/v1/tracking/latest')data={items:[{activity_id:'act_fixture',subscription_id:sid,project_id:pid,name:project.name,x_handle:'fixture_only',notes:'mock',rating:'A',text:'mock 新推文正文',tweet_kind:'original',occurred_at:'2026-10-20T00:00:00.000Z',received_at:'2026-10-20T00:00:01.000Z',url:'https://x.com/fixture_only/status/123'}],matched_total:1,subscription_counts_by_rating:{S:0,A:1,B:0},next_cursor:null};
  else if(url.pathname==='/api/v1/projects/home-summary')data={tracked_total:1,by_rating:{S:0,A:1,B:0},completed_total:0,other_total:0};
  else if(url.pathname==='/api/v1/projects/milestones')data={items:[],as_of_date:'2026-10-20'};
  else if(url.pathname==='/api/v1/projects')data={items:[home],total:1,next_cursor:null};
  else if(url.pathname==='/api/v1/projects/'+pid)data={...project,revision:11};
  else if(url.pathname.startsWith('/api/v1/tracking/subscriptions/'))data={...sub,revision:11};
  else data={items:[],next_cursor:null};
  await new Promise(r=>setTimeout(r,delay));res.setHeader('content-type','application/json');res.end(JSON.stringify({data,request_id:'fixture'}));return;
 }
 res.setHeader('content-type','text/html');res.end('<html><head><style>'+readFileSync(root+'apps/website/app/globals.css','utf8')+'</style><link rel="stylesheet" href="/app.css"/></head><body><div id="root"></div><script>window.process={env:{NODE_ENV:"production"}};</script><script src="/app.js"></script></body></html>');
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});const page=await browser.newPage({viewport:{width:1456,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>{window.SpeechSynthesisUtterance=class{};Object.defineProperty(window,'speechSynthesis',{value:{getVoices:()=>[],addEventListener(){},removeEventListener(){},cancel(){},speak(){}}});});
const rows=()=>page.locator('.hpv2-project-grid tbody tr');
try{
 await page.goto('http://127.0.0.1:'+server.address().port);await rows().first().waitFor();await page.waitForTimeout(600);
 assert.equal(requests.filter(r=>r.path.startsWith('/api/v1/projects?')).length,1,'voice auth must not remount Home');assert.equal(requests.filter(r=>r.path.startsWith('/api/v1/tracking/subscriptions?')).length,1);
 assert.equal(requests.filter(r=>r.path==='/api/v1/tracking/events').length,1);console.log('PASS homepage loads once, root auth/voice does not remount the page');
 let start=requests.length;await page.click('#go-hunter');await page.locator('.v3-table tbody tr').first().waitFor();await page.waitForTimeout(550);
 const hunter=requests.slice(start).filter(r=>r.method==='GET');assert.equal(hunter.filter(r=>r.path.startsWith('/api/v1/hunter/signals?')).length,1,'SSE replay must not reload list');
 const hs=hunter.find(r=>r.path.startsWith('/api/v1/hunter/signals?')),ss=hunter.find(r=>r.path.startsWith('/api/v1/tracking/subscriptions?'));if(ss)assert.ok(Math.abs(hs.at-ss.at)<100);console.log('PASS hunter requests run in parallel; historical SSE causes no duplicate load');
 start=requests.length;await page.click('#go-tracking');await page.locator('article[data-post]').first().waitFor();await page.waitForTimeout(550);
 const tracking=requests.slice(start).filter(r=>r.method==='GET');assert.equal(tracking.filter(r=>r.path.startsWith('/api/v1/tracking/latest?')).length,1);assert.equal(tracking.filter(r=>r.path.startsWith('/api/v1/tracking/subscriptions?')).length,1);
 const a=tracking.find(r=>r.path.startsWith('/api/v1/tracking/subscriptions?')),b=tracking.find(r=>r.path.startsWith('/api/v1/tracking/latest?'));assert.ok(Math.abs(a.at-b.at)<100);assert.equal(requests.filter(r=>r.path==='/api/v1/tracking/events').length,1);console.log('PASS tracking subscriptions + feed parallel, one complete list and one shared SSE');
 delay=1000;
 for(const [target,selector] of [['home','.hpv2-project-grid tbody tr'],['hunter','.v3-table tbody tr'],['tracking','article[data-post]']]){
  const t=Date.now();await page.click('#go-'+target);await page.locator(selector).first().waitFor({timeout:700});assert.ok(Date.now()-t<700);console.log('PASS warm '+target+' renders cache before delayed network completes');await page.waitForTimeout(1100);
 }
 assert.deepEqual(errors,[]);console.log('PASS no browser errors; synthetic GET-only page navigation');
}catch(e){console.log('BROWSER_ERRORS',errors);console.log('REQUESTS',requests.map(r=>r.path));console.log('BODY',(await page.locator('body').innerText()).slice(0,2500));throw e;}finally{await browser.close();for(const res of streams)res.destroy();await new Promise(r=>server.close(r));}
