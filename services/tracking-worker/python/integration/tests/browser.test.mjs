/** Run the entire lifecycle under the chief's shared heavy lock. */
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
const moduleRoot=fileURLToPath(new URL('../../',import.meta.url)),preview=join(moduleRoot,'.b3/preview');
const python=join(moduleRoot,'.venv/bin/python'),fixtureToken=randomUUID(),token='browser-b3-direction-credential-xxxxxxxxxxx';
const dataRoot=realpathSync(mkdtempSync('/private/tmp/ik-b3-browser-'));
const logs=join(moduleRoot,'artifacts/b3/browser-'+Date.now());mkdirSync(logs,{recursive:true});
const {config}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/config.js')));
const {LocalAccounts}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/local.js')));
const {ManagedProjectsIpc,spawnManaged}=await import(pathToFileURL(join(preview,'packages/runtime/dist/index.js')));
async function port(){return new Promise(done=>{const s=createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>done(p));});});}
const sitePort=await port(),trackingPort=await port(),origin='http://127.0.0.1:'+sitePort,tracking='http://127.0.0.1:'+trackingPort;
const initial='Synthetic-B3-Initial-984!',password='Synthetic-B3-Final-Password-274!';
let accounts,manager,engine,website,browser,currentPage,siteEnv;
const steps=[],errors=[],network=[],blockers=[];
async function until(fn,seconds=12){const end=Date.now()+seconds*1000;while(Date.now()<end){try{const result=await fn();if(result)return result;}catch{}await new Promise(r=>setTimeout(r,100));}throw Error('LOCAL_CONDITION_TIMEOUT');}
async function control(body){const r=await fetch(tracking+'/fixture/control',{method:'POST',headers:{'content-type':'application/json','x-fixture-token':fixtureToken},body:JSON.stringify(body)});assert.equal(r.status,200);}
async function internal(path){return(await(await fetch(tracking+'/internal/v1/'+path,{headers:{authorization:'Bearer '+token}})).json()).data;}
async function emit(username,id,text,createdAt){const r=await fetch(tracking+'/fixture/emit',{method:'POST',headers:{'content-type':'application/json','x-fixture-token':fixtureToken},body:JSON.stringify({username,content:{id,text,createdAt,userScreenName:username}})});assert.equal(r.status,200);}
async function startWebsite(){website=spawnManaged(process.execPath,[join(preview,'apps/website/node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',String(sitePort)],{cwd:join(preview,'apps/website'),env:siteEnv,inheritOutput:true,graceMs:3000});await until(async()=>(await fetch(origin+'/login')).ok);}
async function deniedPage(page,response,width,phase){
 if(new URL(page.url()).pathname==='/login'){assert.equal(response.status(),200);return true;}
 const value=await response.json();assert.equal(response.status(),500);assert.equal(value.error?.code,'INTERNAL_ERROR');assert.equal(value.data,undefined);assert.equal(await page.locator('[data-mode="live"]').count(),0);
 blockers.push({code:'AUTH_NEXT_BUNDLE_REJECTION_500',width,phase,status:500,error_code:value.error.code,request_id:value.request_id});await page.screenshot({path:join(logs,'auth-blocked-'+phase+'-'+width+'.png'),fullPage:true});return false;
}
try{
 accounts=new LocalAccounts(config({dataRoot,origin,secure:false}),true);await accounts.bootstrap('admin',initial);await accounts.create('user',initial);
 for(const name of ['admin','user']){const login=await accounts.login(name,initial);await accounts.changePassword(login.actor,initial,password);}
 const entry=join(preview,'modules/projects/integration/ipc-entry.py');
 execFileSync(python,[entry,'--migrate','--database',join(dataRoot,'projects/projects.db')]);
 manager=new ManagedProjectsIpc({executable:python,args:[entry],cwd:join(preview,'modules/projects/candidate'),entry_path:entry,entry_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex'),build_sha:'d0fdefab2aa230ebb8df856aed306d0184d362e2'},dataRoot);
 await manager.start(15000);
 const cfg=join(dataRoot,'tracking.json');writeFileSync(cfg,JSON.stringify({db_path:join(dataRoot,'tracking/tracking.db'),port:trackingPort,remote_enabled:true,dedicated_account:true,reconcile_seconds:.1,backfill_seconds:.2,request_interval:0,heartbeat_seconds:.1,heartbeat_timeout:.5}));
 execFileSync(python,['-m','tracking.cli','init','--config',cfg],{cwd:moduleRoot,env:{...process.env,DATA_ROOT:dataRoot}});
 engine=spawnManaged(python,[join(moduleRoot,'integration/tests/fixture-tracking.py'),cfg,fixtureToken],{cwd:moduleRoot,env:{PATH:process.env.PATH,TRACKING_API_TOKEN:token,IKUN_TRACKING_6551_TOKEN:'synthetic-browser-provider-token'},inheritOutput:true,graceMs:3000});
 await until(async()=>(await fetch(tracking+'/health/ready')).ok);
 siteEnv={PATH:process.env.PATH,NODE_ENV:'production',NEXT_TELEMETRY_DISABLED:'1',DATA_ROOT:dataRoot,IKUN_AUTH_ORIGIN:origin,IKUN_AUTH_DEV:'1',TRACKING_API_TOKEN:token,TRACKING_API_URL:tracking,IKUN_PROJECTS_IPC_SOCKET:manager.identity.socketPath,IKUN_PROJECTS_IPC_TOKEN:manager.identity.token,IKUN_PROJECTS_BUILD_SHA:manager.identity.buildSha};
 await startWebsite();
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:960}});const page=await context.newPage();currentPage=page;
  context.on('page',popup=>popup.on('pageerror',e=>errors.push(e.message)));
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{const url=new URL(r.url());if(url.pathname.startsWith('/api/v1/tracking')||url.pathname==='/api/v1/events/stream')network.push({path:url.pathname,method:r.request().method(),status:r.status()});});
  await context.route('https://x.com/**',r=>r.fulfill({status:200,body:'Synthetic original-link navigation; no external request'}));
  const anonymous=await page.goto(origin+'/tracking');const redirected=await deniedPage(page,anonymous,width,'anonymous');steps.push({width,step:redirected?'anonymous-page-denied':'anonymous-page-fails-closed-BLOCKED-500'});if(!redirected)await page.goto(origin+'/login?next=/tracking');
  await page.locator('input[name="username"]').fill('admin');await page.locator('input[name="password"]').fill(password);await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL('**/tracking');
  await page.waitForSelector('[data-mode="live"]');
  assert.equal(await page.locator('main').count(),1);assert.equal(await page.getByRole('navigation',{name:'业务导航'}).count(),1);
  assert.equal(await page.getByRole('link',{name:'猎手项目追踪',exact:true}).count(),1);
  const me=await(await context.request.get(origin+'/api/v1/auth/me')).json();
  const projectResponse=await context.request.post(origin+'/api/v1/projects',{headers:{origin,'x-csrf-token':me.data.csrf_token,'idempotency-key':randomUUID()},data:{name:'B3浏览器'+width,rating:'A',description:'',website_url:null,notes:'canonical project note stays unchanged',category:null,progress_stage:'watching',progress_percent:null,token_date:null,token_date_status:'unconfirmed'}});assert.equal(projectResponse.status(),201);const project=(await projectResponse.json()).data;
  const handle=width===1440?'project1':'mobilefixture';
  await control({add_noop:true});
  await page.getByRole('button',{name:/监控账号总数/}).click();await page.getByRole('button',{name:'＋ 添加监控账号',exact:true}).click();
  const addForm=page.getByRole('dialog',{name:'监控账号管理',exact:true}).locator('form');await addForm.getByRole('textbox',{name:'已注册项目 ID',exact:true}).fill(project.project_id);await addForm.getByRole('textbox',{name:'项目名称',exact:true}).fill('浏览器监控'+width);await addForm.getByRole('textbox',{name:'X 用户名（不含 @）',exact:true}).fill(handle);await addForm.getByRole('textbox',{name:'监控备注',exact:true}).fill('订阅备注优先 '+width);await addForm.getByRole('checkbox',{name:'我已人工确认项目与 X 账号'}).check();await addForm.getByRole('button',{name:'确认加入监控',exact:true}).click();
  await page.getByText(/cmd_.*(accepted|unknown)/).first().waitFor();
  const sid=await until(async()=>{const list=await internal('subscriptions?include_removed=true');return list.items.find(s=>s.project_id===project.project_id)?.subscription_id;});
  await until(async()=>(await internal('subscriptions/'+sid)).operation_state==='unknown');
  assert.notEqual((await internal('subscriptions/'+sid)).observed_state,'running');steps.push({width,step:'persistent-create-pending-unknown-no-false-running'});
  await control({add_noop:false});await until(async()=>(await internal('subscriptions/'+sid)).operation_state==='succeeded');
  await page.getByRole('button',{name:'编辑',exact:true}).last().waitFor();await page.getByRole('button',{name:'编辑',exact:true}).last().click();
  const edit=page.getByRole('dialog',{name:'编辑监控资料'});await edit.getByLabel('监控备注').fill('真实订阅备注 '+width);await edit.getByRole('button',{name:'保存资料',exact:true}).click();await until(async()=>(await internal('subscriptions/'+sid)).notes==='真实订阅备注 '+width);
  await page.getByRole('button',{name:'停止',exact:true}).last().click();await until(async()=>(await internal('subscriptions/'+sid)).observed_state==='absent');await page.getByText('已停止',{exact:true}).last().waitFor();await page.getByRole('button',{name:'恢复',exact:true}).last().click();await until(async()=>(await internal('subscriptions/'+sid)).observed_state==='running');steps.push({width,step:'edit-stop-resume-real-local-api'});
  // Close management by its cancel-safe close control before examining the live feed.
  await page.keyboard.press('Escape');
  {
   await emit(handle,'101','本地推文正文',new Date().toISOString());await emit(handle,'101','本地推文正文',new Date().toISOString());
   await page.getByText('本地推文正文',{exact:true}).first().waitFor();
   assert.equal(await page.locator('article[data-post]').count(),1);
   const article=page.locator('article[data-post]').first();assert.equal(await article.getByText('真实订阅备注 '+width,{exact:true}).count(),1);
   const noteBox=await article.getByText('真实订阅备注 '+width,{exact:true}).boundingBox(),accountBox=await article.getByText('浏览器监控'+width,{exact:true}).boundingBox();assert.ok(noteBox.x<accountBox.x||noteBox.y<accountBox.y);assert.ok((await article.innerText()).indexOf('真实订阅备注 '+width)<(await article.innerText()).indexOf('浏览器监控'+width));
   assert.ok((await article.innerText()).includes('未知'));const mediaUnknown=article.getByText('媒体信息未提供',{exact:true});assert.equal(await mediaUnknown.count(),1);assert.equal(await mediaUnknown.isVisible(),width>1000);assert.equal(await page.getByRole('checkbox',{name:'只看重要推文'}).isDisabled(),true);
   await page.reload();await page.getByText('本地推文正文',{exact:true}).first().waitFor();assert.equal(await page.locator('article[data-post]').count(),1);
   const popup=page.waitForEvent('popup');await page.getByRole('button',{name:/查看 .* 原文/}).first().click();const original=await popup;await original.waitForLoadState();assert.ok(original.url().startsWith('https://x.com/'));await original.close();steps.push({width,step:'dedup-refresh-notes-first-unknown-fields-safe-original-link'});
  }
  if(width===1440){await website.stop();website=undefined;assert.equal((await internal('status')).alive,true);await emit(handle,'102','网站退出后继续入库',new Date().toISOString());await until(async()=>(await internal('latest')).items.some(item=>item.text==='网站退出后继续入库'));await startWebsite();await page.reload();await page.getByText('网站退出后继续入库',{exact:true}).waitFor();assert.equal(await page.locator('article[data-post]').count(),2);steps.push({width,step:'real-next-stop-engine-continues-restart-recovers-feed'});}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:join(logs,'tracking-'+width+'.png'),fullPage:true});
  const meta=await context.request.get(origin+'/api/v1/projects/'+project.project_id);assert.deepEqual((await meta.json()).data,project);
  await page.getByRole('button',{name:/监控账号总数/}).click();await page.getByRole('button',{name:/删除 浏览器监控/}).last().click();await page.getByRole('button',{name:'确认请求移除',exact:true}).click();await until(async()=>(await internal('subscriptions/'+sid)).observed_state==='absent');await page.keyboard.press('Escape');
  await context.close();
  const userContext=await browser.newContext({viewport:{width,height:960}});const userPage=await userContext.newPage();currentPage=userPage;userPage.on('pageerror',e=>errors.push(e.message));await userPage.goto(origin+'/login?next=/tracking');await userPage.locator('input[name="username"]').fill('user');await userPage.locator('input[name="password"]').fill(password);await userPage.getByRole('button',{name:'登录',exact:true}).click();await userPage.waitForURL('**/tracking');await userPage.waitForSelector('[data-mode="live"]');await userPage.getByRole('button',{name:/监控账号总数/}).click();assert.equal(await userPage.getByRole('button',{name:'＋ 添加监控账号',exact:true}).count(),0);
  const userMe=await(await userContext.request.get(origin+'/api/v1/auth/me')).json();const denied=await userContext.request.post(origin+'/api/v1/tracking/subscriptions',{headers:{origin,'x-csrf-token':userMe.data.csrf_token,'idempotency-key':randomUUID(),'x-role':'superadmin'},data:{project_id:project.project_id,name:'forged',x_handle:'forged',x_user_id:null,notes:'',confirmed:true}});assert.equal(denied.status(),403);
  accounts.setEnabled('user',false);const disabledPage=await userPage.reload();const revokedRedirect=await deniedPage(userPage,disabledPage,width,'disabled');const disabledApi=await userContext.request.get(origin+'/api/v1/tracking/subscriptions');const disabledValue=await disabledApi.json();if(disabledApi.status()!==401){assert.equal(disabledApi.status(),500);assert.equal(disabledValue.error?.code,'INTERNAL_ERROR');assert.equal(disabledValue.data,undefined);blockers.push({code:'AUTH_NEXT_BUNDLE_REJECTION_500',width,phase:'disabled-api',status:500,error_code:disabledValue.error.code,request_id:disabledValue.request_id});}accounts.setEnabled('user',true);steps.push({width,step:revokedRedirect?'user-readonly-server-denied-revoked-cookie':'user-readonly-write-denied-revoked-cookie-fails-closed-BLOCKED-500'});await userContext.close();
 }
 assert.deepEqual(errors,[]);
 const build=JSON.parse(readFileSync(join(moduleRoot,'artifacts/b3/build-inputs.json')));
 const hashes=Object.fromEntries([1440,390].map(width=>['tracking-'+width+'.png',createHash('sha256').update(readFileSync(join(logs,'tracking-'+width+'.png'))).digest('hex')]));
 const receipt={passed:blockers.length===0,completed:true,tracking_flow_passed:true,authorization_full_passed:blockers.length===0,blockers,viewports:[1440,390],steps,network,page_errors:errors,build_id:build.next_build_id,source_set_sha256:build.source_set_sha256,screenshots:hashes,real_provider_calls:0,product_blocked:['C-01','C-03','C-05']};
 writeFileSync(join(logs,'receipt.json'),JSON.stringify(receipt,null,2));writeFileSync(join(moduleRoot,'artifacts/b3/browser-receipt-path.txt'),logs);console.log((blockers.length?'B3_BROWSER_PARTIAL ':'B3_BROWSER_PASS ')+logs);if(blockers.length)process.exitCode=2;
}catch(error){writeFileSync(join(logs,'failure.txt'),String(error.stack||error));writeFileSync(join(logs,'failure-state.json'),JSON.stringify({steps,errors,network,blockers,url:currentPage?.url()},null,2));if(currentPage&&!currentPage.isClosed()){await currentPage.screenshot({path:join(logs,'failure.png'),fullPage:true}).catch(()=>{});writeFileSync(join(logs,'failure.html'),await currentPage.content().catch(()=>''));}throw error;}
finally{if(browser)await browser.close();await website?.stop();await engine?.stop();await manager?.stop();accounts?.close();}
