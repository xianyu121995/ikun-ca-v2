/** Targeted feed regression only; hold the chief's heavy lock for the entire lifetime. */
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createHash,randomUUID} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,realpathSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createServer} from 'node:net';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'/Users/lvlei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const moduleRoot=fileURLToPath(new URL('../../',import.meta.url)),preview=join(moduleRoot,'.b3/preview'),python=join(moduleRoot,'.venv/bin/python');
const build=JSON.parse(readFileSync(join(moduleRoot,'artifacts/b3/build-inputs.json')));
const dataRoot=realpathSync(mkdtempSync('/private/tmp/ik-b3-feed-browser-')),logs=join(moduleRoot,'artifacts/b3/feed-browser-'+Date.now());mkdirSync(logs,{recursive:true});
const {config}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/config.js')));
const {LocalAccounts}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/local.js')));
const {ManagedProjectsIpc,spawnManaged}=await import(pathToFileURL(join(preview,'packages/runtime/dist/index.js')));
const fixtureToken=randomUUID(),token='feed-browser-direction-credential-xxxxxxxxx',initial='Synthetic-Feed-Initial-491!',password='Synthetic-Feed-Password-591!';
async function port(){const s=createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p;}
const sitePort=await port(),trackingPort=await port(),origin='http://127.0.0.1:'+sitePort,tracking='http://127.0.0.1:'+trackingPort;
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await new Promise(r=>setTimeout(r,100));}throw Error('FEED_BROWSER_CONDITION_TIMEOUT');}
async function internal(path){const r=await fetch(tracking+'/internal/v1/'+path,{headers:{authorization:'Bearer '+token}});assert.equal(r.status,200);return(await r.json()).data;}
async function emit(handle,id,text,quote=false){const r=await fetch(tracking+'/fixture/emit',{method:'POST',headers:{'content-type':'application/json','x-fixture-token':fixtureToken},body:JSON.stringify({username:handle,event_type:quote?'NEW_TWEET_QUOTE':'NEW_TWEET',content:{id,text,createdAt:new Date().toISOString(),userScreenName:handle,isReply:false,isQuote:quote,...(quote?{quotedStatus:{userScreenName:'untrackedfixture'}}:{})}})});assert.equal(r.status,200);}
let accounts,manager,engine,website,browser,page;
const steps=[],network=[],errors=[];
try{
 accounts=new LocalAccounts(config({dataRoot,origin,secure:false}),true);await accounts.bootstrap('admin',initial);const first=await accounts.login('admin',initial);await accounts.changePassword(first.actor,initial,password);
 const entry=join(preview,'modules/projects/integration/ipc-entry.py');execFileSync(python,[entry,'--migrate','--database',join(dataRoot,'projects/projects.db')]);
 manager=new ManagedProjectsIpc({executable:python,args:[entry],cwd:join(preview,'modules/projects/candidate'),entry_path:entry,entry_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex'),build_sha:build.pins.projects},dataRoot);await manager.start(15000);
 const cfg=join(dataRoot,'tracking.json');writeFileSync(cfg,JSON.stringify({db_path:join(dataRoot,'tracking/tracking.db'),port:trackingPort,remote_enabled:true,dedicated_account:true,reconcile_seconds:.1,backfill_seconds:.2,request_interval:0,heartbeat_seconds:.1,heartbeat_timeout:.5}));
 execFileSync(python,['-m','tracking.cli','init','--config',cfg],{cwd:moduleRoot,env:{...process.env,DATA_ROOT:dataRoot}});
 engine=spawnManaged(python,[join(moduleRoot,'integration/tests/fixture-tracking.py'),cfg,fixtureToken],{cwd:moduleRoot,env:{PATH:process.env.PATH,TRACKING_API_TOKEN:token,IKUN_TRACKING_6551_TOKEN:'synthetic-feed-provider-not-real'},inheritOutput:true,graceMs:3000});
 await until(async()=>{try{return(await fetch(tracking+'/health/ready')).ok;}catch{return false;}});
 website=spawnManaged(process.execPath,[join(preview,'apps/website/node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',String(sitePort)],{cwd:join(preview,'apps/website'),env:{PATH:process.env.PATH,NODE_ENV:'production',NEXT_TELEMETRY_DISABLED:'1',IKUN_TRACKING_FIXTURE:'1',DATA_ROOT:dataRoot,IKUN_AUTH_ORIGIN:origin,IKUN_AUTH_DEV:'1',TRACKING_API_TOKEN:token,TRACKING_API_URL:tracking,IKUN_PROJECTS_IPC_SOCKET:manager.identity.socketPath,IKUN_PROJECTS_IPC_TOKEN:manager.identity.token,IKUN_PROJECTS_BUILD_SHA:manager.identity.buildSha},inheritOutput:true,graceMs:3000});
 await until(async()=>{try{return(await fetch(origin+'/login')).ok;}catch{return false;}});
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:960}});page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const pendingFeed=new Set();let lastFeedActivity=0,lastFeedIds=[];
  const isFeed=request=>new URL(request.url()).pathname==='/api/v1/tracking/latest';
  page.on('request',request=>{if(isFeed(request)){pendingFeed.add(request);lastFeedActivity=Date.now();}});
  page.on('requestfinished',request=>{if(isFeed(request)){pendingFeed.delete(request);lastFeedActivity=Date.now();}});
  page.on('requestfailed',request=>{if(isFeed(request)){pendingFeed.delete(request);lastFeedActivity=Date.now();}});
  page.on('response',async response=>{if(isFeed(response.request())&&response.ok()){try{lastFeedIds=(await response.json()).data.items.map(item=>item.activity_id);}catch{}}});
  // Initial legacy SSE frames queue a 250ms refresh. Wait for that batch and its DOM commit before using its cursor.
  async function settledFeed(){return until(async()=>{if(pendingFeed.size||Date.now()-lastFeedActivity<350||!lastFeedIds.length)return false;const ids=await page.locator('article[data-post]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('data-post')));return JSON.stringify(ids)===JSON.stringify(lastFeedIds)?ids:false;});}
  page.on('requestfailed',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))network.push({path:new URL(r.url()).pathname,failure:r.failure()?.errorText});});
  await page.goto(origin+'/login?next=/tracking');await page.locator('input[name="username"]').fill('admin');await page.locator('input[name="password"]').fill(password);await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL('**/tracking');await page.waitForSelector('[data-mode="live"]');
  const me=await(await context.request.get(origin+'/api/v1/auth/me')).json(),headers={origin,'x-csrf-token':me.data.csrf_token,'idempotency-key':randomUUID()};
  const created=await context.request.post(origin+'/api/v1/projects',{headers,data:{name:'定向动态夹具'+width,rating:'A',description:'',website_url:null,notes:'canonical fixture',category:null,progress_stage:'watching',progress_percent:null,token_date:null,token_date_status:'unconfirmed'}});assert.equal(created.status(),201);const project=(await created.json()).data,handle='feedfixture'+width;
  const added=await context.request.post(origin+'/api/v1/tracking/subscriptions',{headers:{...headers,'idempotency-key':randomUUID()},data:{project_id:project.project_id,name:project.name,x_handle:handle,x_user_id:null,notes:'定向备注 '+width,confirmed:true}});assert.equal(added.status(),202);const sid=(await added.json()).data.subscription_id;await until(async()=>(await internal('subscriptions/'+sid)).observed_state==='running');
  for(let i=0;i<8;i++)await emit(handle,String(width)+'50'+i,'定向动态 '+width+' '+i);
  await emit(handle,String(width)+'599','定向引用 '+width,true);await emit(handle,String(width)+'599','定向引用 '+width,true);
  const pollingView='qv1_'+randomUUID();await until(async()=>{const r=await context.request.get(origin+'/api/v1/tracking/latest?profile=published-v1&subscription_id='+sid+'&limit=100',{headers:{'x-tracking-query-view':pollingView}});assert.equal(r.status(),200);return(await r.json()).data.items.length===9;});
  await page.reload();await page.getByText('定向引用 '+width,{exact:true}).waitFor();const firstPage=await settledFeed();assert.equal(firstPage.length,6);
  const paged=page.waitForResponse(response=>isFeed(response.request())&&new URL(response.url()).searchParams.has('cursor'));await page.getByRole('button',{name:'下一页',exact:true}).click();const pageResponse=await paged;assert.equal(pageResponse.status(),200);const secondIds=(await pageResponse.json()).data.items.map(item=>item.activity_id);assert.ok(secondIds.length>0&&secondIds.every(id=>!firstPage.includes(id)));await until(async()=>{const ids=await page.locator('article[data-post]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('data-post')));return JSON.stringify(ids)===JSON.stringify(secondIds);});assert.deepEqual(await settledFeed(),secondIds);await page.getByText(/服务端发布时间排序 · 第 2 页/).waitFor();steps.push({width,step:'published-feed-dedup-quote-and-cursor-page'});
  await page.getByRole('button',{name:'S 级',exact:true}).click();await page.getByText('暂无符合条件的推文',{exact:true}).waitFor();assert.equal(await page.locator('article[data-post]').count(),0);await page.getByRole('button',{name:'S/A/B',exact:true}).click();await page.getByRole('searchbox',{name:'搜索推文',exact:true}).fill('定向引用 '+width);await page.getByText('定向引用 '+width,{exact:true}).waitFor();await until(async()=>await page.locator('article[data-post]').count()===1);steps.push({width,step:'SAB-and-Unicode-server-search-after-cursor'});
  const hints=[];for(let i=0;i<10;i++){const pending=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/tracking/latest'&&r.request().method()==='GET');await page.getByRole('button',{name:'刷新',exact:true}).click();const r=await pending;assert.equal(r.status(),200);hints.push(r.request().headers()['x-tracking-query-view']);await r.finished();}assert.equal(new Set(hints).size,1);assert.match(hints[0],/^qv1_/);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);steps.push({width,step:'ten-refreshes-same-view-without-429-or-horizontal-overflow'});
  await page.screenshot({path:join(logs,'feed-'+width+'.png'),fullPage:true});await context.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
 const screenshots=Object.fromEntries([1440,390].map(width=>['feed-'+width+'.png',createHash('sha256').update(readFileSync(join(logs,'feed-'+width+'.png'))).digest('hex')]));
 writeFileSync(join(logs,'receipt.json'),JSON.stringify({passed:true,scope:'targeted-feed-only',steps,viewports:[1440,390],page_errors:errors,network_failures:network,build_id:build.next_build_id,build_source_set_sha256:build.source_set_sha256,preview_source_set_sha256:build.preview_source_set_sha256,test_source_sha256:createHash('sha256').update(readFileSync(fileURLToPath(import.meta.url))).digest('hex'),screenshots,real_provider_calls:0},null,2));writeFileSync(join(moduleRoot,'artifacts/b3/feed-browser-receipt-path.txt'),logs);console.log('B3_FEED_BROWSER_PASS '+logs);
}catch(error){writeFileSync(join(logs,'failure.json'),JSON.stringify({message:String(error.stack||error),steps,errors,network},null,2));if(page&&!page.isClosed())await page.screenshot({path:join(logs,'failure.png'),fullPage:true}).catch(()=>{});throw error;}
finally{await browser?.close();await website?.stop();await engine?.stop();await manager?.stop();accounts?.close();}
