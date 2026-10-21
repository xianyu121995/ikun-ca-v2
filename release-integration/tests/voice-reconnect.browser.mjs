/** Isolated real-Chrome/real-EventSource regression. No production accounts, data, sound or provider calls. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {Readable} from 'node:stream';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {withSseHeartbeat} from '../../apps/website/lib/sse-heartbeat.ts';
const require=createRequire(import.meta.url);
const {build}=require('../../packages/ui/node_modules/esbuild');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=fileURLToPath(new URL('../../',import.meta.url));
const bundle=await build({stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import {VoiceDock,useSiteVoice} from './components/voice-dock';function Probe(){const c=useSiteVoice();React.useEffect(()=>{window.__voiceController=c;},[c]);return <button id="gesture">测试页面</button>;}createRoot(document.getElementById('root')).render(<VoiceDock><Probe/></VoiceDock>);`,resolveDir:root+'apps/website',loader:'tsx'},bundle:true,write:false,format:'iife',jsx:'automatic',define:{'process.env.NODE_ENV':'"production"'}});
const streams=new Set();let loggedIn=true,connections=0,feedAvailable=true;const feedItems=[];
const uid='usr_00000000-0000-4000-8000-000000000001';
const emptyNotesSub='sub_d4bf0a2e-00dc-49f8-bbf3-a1231bcb7475',canonicalProject='prj_779afd82-bc46-4293-9735-1b47863fc7a5';
const server=createServer((req,res)=>{
  if(req.url==='/app.js'){res.setHeader('content-type','text/javascript');res.end(bundle.outputFiles[0].contents);return;}
  if(req.url==='/api/v1/auth/me'){
    res.writeHead(loggedIn?200:401,{'content-type':'application/json'});
    res.end(JSON.stringify(loggedIn?{data:{user_id:uid,role:'user',must_change_password:false},request_id:'voice_fixture'}:{error:'signed-out'}));return;
  }
  if(req.url==='/api/v1/tracking/events'){
    if(!loggedIn){res.writeHead(401);res.end();return;}
    connections++;streams.add(res);const abort=new AbortController();
    const response=withSseHeartbeat(new Response(new ReadableStream({cancel(){}}),{headers:{'content-type':'text/event-stream'}}),abort.signal);
    res.writeHead(response.status,Object.fromEntries(response.headers));Readable.fromWeb(response.body).pipe(res);
    res.on('close',()=>{streams.delete(res);abort.abort();});return;
  }
  if(req.url?.startsWith('/api/v1/tracking/latest?')){
    res.writeHead(feedAvailable?200:503,{'content-type':'application/json','x-ikun-server-time':new Date().toISOString()});
    res.end(JSON.stringify({data:{profile:'published-v1',items:feedItems,next_cursor:null},request_id:'voice_fixture'}));return;
  }
  if(req.url?.startsWith('/api/')){
    let data={items:[],next_cursor:null};
    if(req.url==='/api/v1/tracking/subscriptions/'+emptyNotesSub)data={subscription_id:emptyNotesSub,project_id:canonicalProject,revision:1,notes:'',name:'订阅别名不能代替项目名称'};
    if(req.url==='/api/v1/projects/'+canonicalProject)data={project_id:canonicalProject,revision:2,name:'挖矿挖AI，用GPU',rating:'B'};
    res.setHeader('content-type','application/json');res.end(JSON.stringify({data,request_id:'voice_fixture'}));return;
  }
  res.setHeader('content-type','text/html');res.end(`<html><head><style>${readFileSync(root+'apps/website/app/globals.css','utf8')}</style></head><body><div id="root"></div><script src="/app.js"></script></body></html>`);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
const context=await browser.newContext({viewport:{width:1400,height:820}});
await context.addInitScript(()=>{
  window.__voiceAuditions=[];window.__voiceAuditionMode='success';
  window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
  Object.defineProperty(window,'speechSynthesis',{value:{getVoices:()=>[{localService:true,lang:'zh-CN',default:true}],addEventListener(){},removeEventListener(){},cancel(){},speak(utterance){window.__voiceLast=utterance;window.__voiceAuditions.push(utterance.text);if(window.__voiceAuditionMode==='error')queueMicrotask(()=>utterance.onerror?.());else {utterance.onstart?.();if(window.__voiceAuditionMode!=='hold')queueMicrotask(()=>utterance.onend?.());}}}});
});
const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
const waitState=state=>page.waitForFunction(value=>document.querySelector('.ikun-voice-dock')?.dataset.state===value,state);
const disconnect=()=>{for(const res of streams)res.destroy();};
const addFeed=(packet,name='中文测试项目',rating='B',age=1000)=>{feedItems.unshift({activity_id:packet.activity_id,subscription_id:packet.subscription_id,project_id:packet.project_id,name,rating,occurred_at:new Date(Date.now()-age).toISOString()});};
const notify=(packet)=>{for(const res of streams)res.write(`id: evt_${crypto.randomUUID()}\nevent: tracking.feed.activity.updated.v1\ndata: ${JSON.stringify({data:packet,request_id:'voice_fixture'})}\n\n`);};
try{
  await page.goto(`http://127.0.0.1:${server.address().port}`);await waitState('off');await page.waitForFunction(()=>window.__voiceController?.getSnapshot().connected===true);
  await page.click('#gesture');await waitState('on');
  assert.equal(await page.evaluate(()=>navigator.userActivation.hasBeenActive),true);
  let count=connections;feedAvailable=false;disconnect();await waitState('locked');addFeed({activity_id:'act_'+crypto.randomUUID(),subscription_id:emptyNotesSub,project_id:canonicalProject},'断线恢复新项目','A');feedAvailable=true;
  await page.waitForFunction(()=>document.querySelector('.ikun-voice-dock')?.dataset.state==='on',null,{timeout:15_000});
  assert.ok(connections>count);await page.waitForFunction(()=>window.__voiceAuditions.includes('断线恢复新项目，A级。'),null,{timeout:5000});await page.evaluate(()=>{window.__voiceAuditions=[];});console.log('PASS enable → real SSE socket disconnect → auto reconnect: 语音开');
  await page.locator('.ikun-voice-fab').click();
  assert.deepEqual(await page.evaluate(()=>window.__voiceAuditions),[]);
  await page.getByRole('button',{name:'试听语音',exact:true}).click();
  await page.getByText(/^浏览器已完成试听/).waitFor();
  assert.deepEqual(await page.evaluate(()=>window.__voiceAuditions),['这是 ikun 语音测试。Voice test, one two three.']);await waitState('on');
  console.log('PASS audition requires a click, uses the browser speech adapter, changes no global preference');
  await page.evaluate(()=>{window.__voiceAuditionMode='hold';});await page.getByRole('button',{name:'试听语音',exact:true}).click();
  await page.getByText('浏览器正在播放试听。',{exact:true}).waitFor();
  const packet={activity_id:'act_'+crypto.randomUUID(),subscription_id:'sub_'+crypto.randomUUID(),project_id:'prj_'+crypto.randomUUID(),source:'wss',tweet_kind:'original',is_live_new:true,replay:false,received_at:new Date().toISOString()};
  addFeed(packet);notify(packet);
  await page.getByText('实时播报优先，试听已停止。',{exact:true}).waitFor();
  await page.evaluate(()=>window.__voiceLast.onend?.());
  console.log('PASS new published feed row stops audition before speaking');
  await page.evaluate(()=>{window.__voiceAuditionMode='error';});
  await page.getByRole('button',{name:'试听语音',exact:true}).click();await page.getByText(/^浏览器播放试听失败/).waitFor();await waitState('on');
  console.log('PASS browser rejects audition: report failure without muting or corrupting live voice');
  await page.evaluate(()=>{window.__voiceAuditionMode='success';});
  const livePacket={...packet,activity_id:'act_'+crypto.randomUUID(),subscription_id:emptyNotesSub,project_id:canonicalProject,received_at:new Date().toISOString(),project_name:'不可信事件名称',notes:'不可信事件备注'};
  addFeed(livePacket,'挖矿挖AI，用GPU');notify(livePacket);
  await page.waitForFunction(()=>window.__voiceAuditions.at(-1)==='挖矿挖AI，用GPU，B级。');
  console.log('PASS SSE notification → authenticated published list → project name + B grade');
  const other=await context.newPage();await other.goto(`http://127.0.0.1:${server.address().port}`);await other.locator('.ikun-voice-dock').waitFor();await other.click('#gesture');
  assert.deepEqual(await other.evaluate(()=>window.__voiceAuditions),[],'initial list in a new tab is silent');
  const restPacket={...livePacket,activity_id:'act_'+crypto.randomUUID(),source:'rest',tweet_kind:'unknown',replay:true,is_live_new:false};
  addFeed(restPacket,'REST未知类型项目','A');notify(restPacket);
  await page.waitForFunction(()=>window.__voiceAuditions.includes('REST未知类型项目，A级。'));
  notify(restPacket);await new Promise(r=>setTimeout(r,300));
  const spoken=(await page.evaluate(()=>window.__voiceAuditions)).concat(await other.evaluate(()=>window.__voiceAuditions));
  assert.equal(spoken.filter(x=>x==='REST未知类型项目，A级。').length,1);
  console.log('PASS REST/unknown published item speaks once across two real Chrome tabs; duplicate SSE stays silent');
  addFeed({...restPacket,activity_id:'act_'+crypto.randomUUID()},'过旧项目','B',660000);notify(restPacket);await new Promise(r=>setTimeout(r,300));
  assert.ok(!(await page.evaluate(()=>window.__voiceAuditions)).includes('过旧项目，B级。'));
  const fallback={...restPacket,activity_id:'act_'+crypto.randomUUID()};addFeed(fallback,'轮询新项目','S');
  await page.waitForFunction(()=>window.__voiceAuditions.includes('轮询新项目，S级。'),null,{timeout:18000});
  console.log('PASS 15-second fallback polling speaks a new item without SSE; >10-minute item remains silent');
  await other.close();
  await page.getByRole('button',{name:'关闭语音',exact:true}).click();await waitState('off');
  await page.evaluate(()=>{window.__voiceAuditionMode='success';});
  await page.getByRole('button',{name:'试听语音',exact:true}).click();await page.getByText(/^浏览器已完成试听/).waitFor();await waitState('off');
  console.log('PASS explicit one-shot audition does not turn global voice back on when manually muted');
  count=connections;disconnect();for(let n=0;n<150&&connections===count;n++)await new Promise(r=>setTimeout(r,100));
  assert.ok(connections>count);await waitState('off');
  await page.reload();await waitState('off');await page.click('#gesture');await waitState('off');
  console.log('PASS manual off remains off after reconnect and reload + click');
  await page.locator('.ikun-voice-fab').click();await page.getByRole('button',{name:'启用本页语音',exact:true}).click();await waitState('on');
  await page.reload();await waitState('locked');
  const style=await page.locator('.ikun-voice-fab').evaluate(el=>({bg:getComputedStyle(el).backgroundColor,animation:getComputedStyle(el).animationName}));
  assert.equal(style.bg,'rgb(251, 146, 60)');assert.equal(style.animation,'ikun-voice-attention');
  console.log('PASS true lock: orange blinking button; no automatic unlock on a fresh page');
  await page.click('#gesture');await waitState('on');loggedIn=false;disconnect();await waitState('off');
  await page.click('#gesture');await waitState('off');console.log('PASS logout/revocation prevents reactivation');
  assert.deepEqual(errors,[]);
}finally{
  await browser.close();disconnect();await new Promise(resolve=>server.close(resolve));
}
