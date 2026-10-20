/** Isolated Chrome + mock API: never connects to production, providers or Watch. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url),{build}=require('../../packages/ui/node_modules/esbuild');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=fileURLToPath(new URL('../../',import.meta.url));
const pid='prj_779afd82-bc46-4293-9735-1b47863fc7a5';
const bundle=await build({stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import {JoinProjectTracking} from './components/join-project-tracking';import {TrackingHomeEditor} from './components/tracking-home-editor';
const params=new URLSearchParams(location.search),admin=!params.has('reader');const target={project_id:'${pid}',name:'测试项目',tweet:'纯 mock 测试'};
createRoot(document.getElementById('root')).render(params.has('editor')?<TrackingHomeEditor target={target} csrf="fixture-csrf" canManage={admin} onClose={()=>{}} onSaved={()=>{}}/>:<form onSubmit={e=>{e.preventDefault();window.__saved=true;}}><JoinProjectTracking projectId="${pid}" csrf="fixture-csrf" canManage={admin} onJoined={()=>window.__joined=true}/><button type="submit">保存项目</button></form>);`,resolveDir:root+'apps/website',loader:'tsx'},bundle:true,write:false,format:'iife',jsx:'automatic',define:{'process.env.NODE_ENV':'"production"'}});
let mode='already',posts=[],failOnce=false;
const server=createServer(async(req,res)=>{
 if(req.url==='/app.js'){res.setHeader('content-type','text/javascript');res.end(bundle.outputFiles[0].contents);return;}
 if(req.url?.startsWith('/api/')){
  let data;
  if(req.url.startsWith('/api/v1/projects/'))data={project:{project_id:pid,name:'测试项目',revision:7,notes:'',progress_stage:'researching',category:null,home_membership:'active'},milestone:{date:null,hour:null,title:'',status:'unconfirmed'},completion:null};
  else if(req.method==='POST'){
   const chunks=[];for await(const chunk of req)chunks.push(chunk);
   posts.push({body:JSON.parse(Buffer.concat(chunks).toString()),headers:req.headers});
   await new Promise(r=>setTimeout(r,100));
   if(mode==='fail'||mode==='retry'&&!failOnce){failOnce=true;res.writeHead(503,{'content-type':'application/json'});res.end(JSON.stringify({error:{message:'模拟接口失败，请稍后核对'}}));return;}
   data={status:'added',message:'已加入追踪',project_revision:7};
  }else data=mode==='already'||mode==='stopped'?{status:'already',message:mode==='stopped'?'已在追踪列表（已停止，可到追踪页恢复）':'已在追踪列表',project_revision:7}:{status:'ready',x_handle:mode==='manual'?null:'testaccount',project_revision:7};
  res.setHeader('content-type','application/json');res.end(JSON.stringify({data,request_id:'fixture'}));return;
 }
 res.setHeader('content-type','text/html');res.end('<html><body><div id="root"></div><script src="/app.js"></script></body></html>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
const page=await browser.newPage({viewport:{width:1400,height:820}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const open=async(next,query='')=>{mode=next;posts=[];failOnce=false;await page.goto('http://127.0.0.1:'+server.address().port+'/'+query);};
try{
 await open('already','?reader');assert.equal(await page.getByRole('button',{name:'加入追踪',exact:true}).count(),0);
 await open('already','?reader&editor');await page.getByRole('button',{name:'保存并同步到主页'}).waitFor();assert.equal(await page.getByRole('button',{name:'加入追踪',exact:true}).count(),0);console.log('PASS read-only: button hidden in both entry points');
 for(const next of ['already','stopped']){
  await open(next);await page.getByRole('button',{name:'加入追踪',exact:true}).click();await page.getByRole('status').waitFor();assert.match(await page.getByRole('status').textContent(),/已在追踪列表/);if(next==='stopped')assert.match(await page.getByRole('status').textContent(),/已停止/);assert.equal(posts.length,0);
 }console.log('PASS tracked/stopped: exact duplicate message, no POST or resume');
 await open('automatic');await page.getByRole('button',{name:'加入追踪',exact:true}).dblclick();await page.getByText('已加入追踪',{exact:true}).waitFor();assert.equal(posts.length,1);assert.deepEqual(posts[0].body,{x_handle:'testaccount'});assert.equal(posts[0].headers['if-match'],'"rev-7"');assert.equal(posts[0].headers['x-csrf-token'],'fixture-csrf');assert.match(posts[0].headers['idempotency-key'],/^[0-9a-f-]{36}$/);assert.equal(await page.evaluate(()=>!!window.__saved),false);assert.equal(await page.evaluate(()=>window.__joined),true);console.log('PASS automatic handle, revision + CSRF + idempotency, rapid double click produces one mock request');
 await open('manual');await page.getByRole('button',{name:'加入追踪',exact:true}).click();await page.getByLabel('X 用户名',{exact:true}).fill('bad-name');await page.getByRole('button',{name:'确认加入'}).click();await page.getByRole('alert').waitFor();assert.equal(posts.length,0);await page.getByLabel('X 用户名',{exact:true}).fill('@Manual_123');await page.getByLabel('X 用户名',{exact:true}).press('Enter');await page.getByText('已加入追踪',{exact:true}).waitFor();assert.equal(posts.length,1);assert.equal(posts[0].body.x_handle,'manual_123');assert.equal(await page.evaluate(()=>!!window.__saved),false);console.log('PASS manual prompt, validation, Enter does not save project');
 await open('retry');await page.getByRole('button',{name:'加入追踪',exact:true}).click();await page.getByRole('alert').waitFor();const key=posts[0].headers['idempotency-key'];await page.getByRole('button',{name:'加入追踪',exact:true}).click();await page.getByText('已加入追踪',{exact:true}).waitFor();assert.equal(posts.length,2);assert.equal(posts[1].headers['idempotency-key'],key);console.log('PASS failed/uncertain retry preserves idempotency key');
 await open('already','?editor');await page.getByRole('button',{name:'加入追踪',exact:true}).click();await page.getByText('已在追踪列表',{exact:true}).waitFor();assert.equal(posts.length,0);console.log('PASS tweet homepage editor uses same action without any project save');
 assert.deepEqual(errors,[]);
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
