const {chromium}=require(process.env.HUNTER_PLAYWRIGHT_MODULE);
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const base=process.env.IKUN_AUTH_ORIGIN,out=process.env.B4_BROWSER_EVIDENCE;
const initial='B4-fixture-initial-passphrase',active='B4-fixture-active-passphrase';
const passed=[],errors=[],external=[];
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const page=await context.newPage();page.setDefaultTimeout(10000);
 async function watch(p){p.on('pageerror',e=>errors.push(e.message));await p.route('**/*',route=>{if(!route.request().url().startsWith(base)){external.push(route.request().url());return route.abort();}return route.continue();});}
 await watch(page);
 const check=async(name,fn)=>{await fn();passed.push(name);console.log('PASS '+name);};
 const rows=()=>page.locator('.ik-table tbody tr');
 async function loaded(p=page){await p.locator('.ik-table tbody tr .account').first().waitFor();}
 async function login(p,username,password=initial,force=true){
  await p.goto(base+'/login?next=%2Fhunter');await p.locator('input[name="username"]').fill(username);await p.locator('input[name="password"]').fill(password);await p.getByRole('button',{name:'登录',exact:true}).click();
  if(force){await p.waitForURL('**/auth/password');assert.equal(await p.locator('input[name="new_password"]').getAttribute('minlength'),'10');await p.locator('input[name="current_password"]').fill(initial);await p.locator('input[name="new_password"]').fill(active);await p.locator('input[name="confirm_password"]').fill(active);await p.getByRole('button',{name:'保存新密码'}).click();await p.waitForURL('**/?notice=password_changed');await p.goto(base+'/hunter');}
  await loaded(p);
 }
 async function reset(){await page.getByRole('button',{name:/重置/}).click();await page.waitForTimeout(250);await loaded();}
 async function editor(){await page.getByRole('button',{name:'研究 / 编辑',exact:true}).first().click();await page.locator('.drawer').waitFor();await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='项目名称');}
 async function close(){await page.getByRole('button',{name:/收起资料/}).click();}
 async function action(p,row,csrf){
  await p.goto(base+'/internal/v1/hunter-action-probe');
  for(const [name,value] of Object.entries({discovery_id:row.discovery_id,revision:String(row.revision),key:crypto.randomUUID(),csrf,project:JSON.stringify(row.project)}))await p.locator('[name="'+name+'"]').fill(value);
  await p.getByRole('button',{name:'Execute fixture action',exact:true}).click();await p.waitForURL('**/internal/v1/hunter-action-probe?status=*');
  return Number(await p.getByLabel('Action result').innerText());
 }
 async function state(){return (await (await page.request.get(base+'/api/v1/hunter/accounts?limit=100')).json()).data.items;}
 async function manage(action,handle){
  await page.getByRole('button',{name:/猎手管理/}).click();const dialog=page.getByRole('dialog');await dialog.getByLabel('选择操作').selectOption(action);await dialog.getByLabel('X 用户名',{exact:true}).fill(handle);await dialog.getByRole('button',{name:'确认执行',exact:true}).click();return dialog;
 }
 try{
  await check('匿名页面与API拒绝，真实B1首次改密',async()=>{
   const denied=await page.request.get(base+'/api/v1/hunter/signals');assert.equal(denied.status(),401);
   await page.goto(base+'/hunter');await page.waitForURL('**/login?next=*');
   await login(page,'fixture_admin');
  });
  await check('唯一公共组件与全宽默认表，C-04真实保存入口',async()=>{
   assert.equal(await page.locator('.ik-shell').count(),1);assert.equal(await page.locator('.drawer').count(),0);
   const navigation=await page.evaluate(()=>{const link=document.querySelector('a[href="/tracking"]');let result;window.addEventListener('click',event=>{result={href:link.getAttribute('href'),defaultPrevented:event.defaultPrevented};event.preventDefault();},{once:true});link.click();return result;});
   assert.deepEqual(navigation,{href:'/tracking',defaultPrevented:false});
   assert.equal(await rows().count(),10);const width=(await page.locator('.discovery').boundingBox()).width;
   const handle=(await rows().first().locator('.account small').innerText()).slice(1);
   await page.evaluate(()=>{window.__originalOpen=window.open;window.open=(...args)=>{window.__opened=args;return null;};});
   await page.getByRole('button',{name:'X 主页 ↗',exact:true}).first().click();
   assert.deepEqual(await page.evaluate(()=>{window.open=window.__originalOpen;return window.__opened;}),['https://x.com/'+handle,'_blank','noopener,noreferrer']);
   await editor();assert.ok((await page.locator('.discovery').boundingBox()).width<width);
   assert.equal(await page.getByRole('button',{name:'▣ 保存项目资料'}).isDisabled(),false);
   assert.match(await page.locator('.drawer-note').innerText(),/未连接真实来源/);
   assert.match(await page.locator('.prototype-chip').innerText(),/本地验收夹具.*未连接真实来源/);
   await close();assert.equal((await page.locator('.discovery').boundingBox()).width,width);
  });
  await check('真实服务端搜索、评分筛选与跨100条游标分页',async()=>{
   await page.getByRole('searchbox',{name:'搜索项目'}).fill('fixture_p111');await page.waitForFunction(()=>document.querySelectorAll('.ik-table tbody tr').length===1);
   assert.match(await rows().first().innerText(),/fixture_p111/);await reset();
   await page.getByRole('button',{name:'S',exact:true}).first().click();await page.getByText('没有符合条件的项目',{exact:true}).waitFor();await reset();
   const seen=new Set();for(let i=0;i<11;i++){for(const text of await rows().allInnerTexts())seen.add(text.match(/@fixture_p\d+/)[0]);if(i<10){const previous=await rows().first().innerText(),cursorResponse=i===9?page.waitForResponse(r=>r.ok()&&r.url().includes('/api/v1/hunter/signals?')&&new URL(r.url()).searchParams.has('cursor')):null;await page.getByRole('button',{name:'下一页',exact:true}).click();if(cursorResponse){const next=(await (await cursorResponse).json()).data;await page.waitForFunction(handles=>handles.includes(document.querySelector('.ik-table tbody tr .account small')?.textContent?.slice(1)),next.items.map(item=>item.x_handle));}else await page.waitForFunction(old=>document.querySelector('.ik-table tbody tr')?.innerText!==old,previous);}}
   assert.ok(seen.size>100,'server cursor page must not silently stop at first 100');await page.reload();await loaded();
  });
  await check('未保存资料取消/放弃及焦点恢复',async()=>{
   const trigger=page.getByRole('button',{name:'研究 / 编辑',exact:true}).first();await trigger.click();await page.getByLabel('项目名称',{exact:true}).fill('unsaved fixture');await close();
   await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();assert.equal(await page.getByLabel('项目名称',{exact:true}).inputValue(),'unsaved fixture');
   await close();await page.getByRole('dialog').getByRole('button',{name:'放弃修改',exact:true}).click();await page.locator('.drawer').waitFor({state:'detached'});assert.equal(await trigger.evaluate(e=>e===document.activeElement),true);
  });
  await check('真实研究PATCH最小回执、重复点击防护、刷新持久',async()=>{
   await editor();await page.getByLabel('项目名称',{exact:true}).fill('B4 Research Fixture');await page.getByLabel('个人备注 / 进度',{exact:true}).fill('Research persisted <script>inert()</script>');
   let sends=0;const count=request=>{if(request.method()==='PATCH'&&/\/discoveries\/dsc_[^/]+$/.test(request.url()))sends++;};page.on('request',count);
   const response=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes('/discoveries/'));
   await page.getByRole('button',{name:'▣ 保存项目资料'}).evaluate(button=>{button.click();button.click();});
   const saved=await response;assert.equal(saved.status(),200);const result=(await saved.json()).data;assert.deepEqual(Object.keys(result).sort(),['discovery_id','revision','saved_at']);
   await page.getByText('研究资料已保存。',{exact:true}).waitFor();assert.equal(sends,1);page.off('request',count);
   await close();assert.equal(await page.getByRole('dialog').count(),0);
   await page.reload();await loaded();const current=(await (await page.request.get(base+'/api/v1/hunter/discoveries/'+result.discovery_id)).json()).data;
   assert.equal(current.project.name,'B4 Research Fixture');assert.equal(current.project.notes,'Research persisted <script>inert()</script>');assert.equal(current.project_id,null);assert.equal(current.revision,result.revision);
   for(const grade of ['C','D']){
    const row=(await (await page.request.get(base+'/api/v1/hunter/discoveries/'+result.discovery_id)).json()).data,me=(await (await page.request.get(base+'/api/v1/auth/me')).json()).data;
    assert.equal((await page.request.patch(base+'/api/v1/hunter/discoveries/'+result.discovery_id,{headers:{origin:base,'x-csrf-token':me.csrf_token,'if-match':'"rev-'+row.revision+'"','idempotency-key':crypto.randomUUID()},data:{rating:grade}})).status(),200);
    await page.reload();await loaded();await editor();assert.equal(await page.getByRole('button',{name:grade,exact:true}).getAttribute('aria-pressed'),'true');
    await page.getByLabel('个人备注 / 进度',{exact:true}).fill('Preserve rating '+grade);await page.getByRole('button',{name:'▣ 保存项目资料'}).click();await page.waitForFunction(()=>!document.querySelector('.dirty-dot'));
    const saved=(await (await page.request.get(base+'/api/v1/hunter/discoveries/'+result.discovery_id)).json()).data;assert.equal(saved.project.rating,grade);assert.equal(saved.project.notes,'Preserve rating '+grade);await close();
   }
  });
  await check('研究409保留草稿，丢ACK复用UUID核对且不重复写',async()=>{
   const handle=(await rows().first().locator('.account small').innerText()).slice(1);const info=(await (await page.request.get(base+'/api/v1/hunter/signals?limit=100')).json()).data.items.find(item=>item.x_handle===handle),target=base+'/api/v1/hunter/discoveries/'+info.discovery_id;
   const me=(await (await page.request.get(base+'/api/v1/auth/me')).json()).data;
   await editor();await page.getByLabel('个人备注 / 进度',{exact:true}).fill('Conflict research draft');
   assert.equal((await page.request.patch(target,{headers:{origin:base,'x-csrf-token':me.csrf_token,'if-match':'"rev-'+info.revision+'"','idempotency-key':crypto.randomUUID()},data:{notes:'Concurrent fixture'}})).status(),200);
   let pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url()===target);await page.getByRole('button',{name:'▣ 保存项目资料'}).click();assert.equal((await pending).status(),409);
   await page.getByText('发现记录已变更',{exact:true}).first().waitFor();assert.equal(await page.getByLabel('个人备注 / 进度',{exact:true}).inputValue(),'Conflict research draft');
   await page.reload();await loaded();await editor();await page.getByLabel('个人备注 / 进度',{exact:true}).fill('Lost ACK research');
   const keys=[];let committedRevision;
   await page.route(target,async route=>{if(route.request().method()!=='PATCH')return route.continue();keys.push(route.request().headers()['idempotency-key']);if(keys.length===1){const real=await route.fetch();assert.equal(real.status(),200);committedRevision=(await real.json()).data.revision;return route.fulfill({status:504,contentType:'application/json',body:JSON.stringify({error:{code:'UPSTREAM_TIMEOUT',message:'fixture lost acknowledgement',retryable:true},request_id:'fixture-lost'})});}return route.continue();});
   pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url()===target);await page.getByRole('button',{name:'▣ 保存项目资料'}).click();assert.equal((await pending).status(),504);
   await page.getByText('fixture lost acknowledgement',{exact:true}).first().waitFor();assert.equal(await page.getByRole('button',{name:'结果待核实',exact:true}).isDisabled(),true);
   pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url()===target);await page.getByRole('button',{name:'▣ 保存项目资料'}).click();assert.equal((await pending).status(),200);
   await page.getByText('研究资料已保存。',{exact:true}).waitFor();assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);
   const current=(await (await page.request.get(target)).json()).data;assert.equal(current.revision,committedRevision);assert.equal(current.project.notes,'Lost ACK research');
   await page.unroute(target);await page.reload();await loaded();
  });
  await check('管理员猎手添加/启用/停用/移除为真实hunter.db操作且不展示名单',async()=>{
   let dialog=await manage('add','qa_hunter');await page.waitForFunction(()=>document.querySelector('.ik-toasts')?.textContent.includes('本地配置已保存'));
   assert.equal((await state()).find(x=>x.x_handle==='qa_hunter').enabled,false);assert.equal(await page.getByText('@fixture_hunter1',{exact:true}).count(),0);await dialog.getByRole('button',{name:'关闭',exact:true}).click();
   dialog=await manage('enable','qa_hunter');await page.waitForTimeout(350);assert.equal((await state()).find(x=>x.x_handle==='qa_hunter').enabled,true);await dialog.getByRole('button',{name:'关闭',exact:true}).click();
   dialog=await manage('disable','qa_hunter');await dialog.getByRole('button',{name:'取消',exact:true}).click();assert.equal((await state()).find(x=>x.x_handle==='qa_hunter').enabled,true);await page.getByRole('dialog').getByRole('button',{name:'关闭',exact:true}).click();
   dialog=await manage('disable','qa_hunter');await dialog.getByRole('button',{name:'确认停用',exact:true}).click();await page.waitForTimeout(350);assert.equal((await state()).find(x=>x.x_handle==='qa_hunter').enabled,false);await page.getByRole('dialog').getByRole('button',{name:'关闭',exact:true}).click();
   dialog=await manage('remove','qa_hunter');await dialog.getByRole('button',{name:'确认移除',exact:true}).click();await page.waitForTimeout(350);assert.equal((await state()).find(x=>x.x_handle==='qa_hunter'),undefined);await page.getByRole('dialog').getByRole('button',{name:'关闭',exact:true}).click();
  });
  await check('人工确认取消/重复点击防护/202待核实及刷新持久化',async()=>{
   await editor();await page.getByLabel('项目名称',{exact:true}).fill('B4 Confirmed Fixture');await page.getByLabel('个人备注 / 进度',{exact:true}).fill('Persistent note <script>inert()</script>');
   const join=page.getByRole('button',{name:'＋ 加入猎手项目监控',exact:true});await join.click();await page.getByRole('dialog').getByRole('button',{name:'取消',exact:true}).click();
   let sends=0;const count=request=>{if(request.method()==='POST'&&request.url().includes('/monitoring-requests'))sends++;};page.on('request',count);
   await join.click();await page.getByRole('dialog').getByRole('button',{name:'确认提交',exact:true}).evaluate(button=>{button.click();button.click();});
   await page.getByRole('dialog').waitFor({state:'hidden'});assert.equal(sends,1);page.off('request',count);
   await page.waitForFunction(()=>document.querySelector('.drawer-action')?.textContent.includes('结果待核实'));assert.equal(await page.getByRole('button',{name:'结果待核实',exact:true}).isDisabled(),true);
   await page.reload();await loaded();const result=await (await page.request.get(base+'/api/v1/hunter/signals?q=B4%20Confirmed%20Fixture')).json();assert.equal(result.data.items.length,1);assert.equal(result.data.items[0].monitoring_state,'pending');assert.match(result.data.items[0].project.notes,/Persistent note/);
  });
  await check('409冲突保留草稿，未知结果禁止重复确认',async()=>{
   await page.getByRole('button',{name:'研究 / 编辑',exact:true}).nth(1).click();await page.getByLabel('项目名称',{exact:true}).fill('Conflict draft');
   let code='VERSION_CONFLICT',status=409;await page.route('**/monitoring-requests',route=>route.fulfill({status,contentType:'application/json',body:JSON.stringify({error:{code,message:'fixture '+code,retryable:false},request_id:'fixture-response'})}));
   await page.getByRole('button',{name:'＋ 加入猎手项目监控',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'确认提交',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});assert.equal(await page.getByLabel('项目名称',{exact:true}).inputValue(),'Conflict draft');
   code='UPSTREAM_TIMEOUT';status=504;await page.getByRole('button',{name:'＋ 加入猎手项目监控',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'确认提交',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});assert.equal(await page.getByRole('button',{name:'结果待核实',exact:true}).isDisabled(),true);assert.equal(await page.getByLabel('项目名称',{exact:true}).inputValue(),'Conflict draft');
   await page.unroute('**/monitoring-requests');await page.reload();await loaded();
  });
  await check('刷新期间保留旧行、请求失败显示错误、不回退演示',async()=>{
   const before=await rows().count();let release;const barrier=new Promise(resolve=>release=resolve);
   await page.route('**/api/v1/hunter/signals?**',async route=>{await barrier;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'DB_UNAVAILABLE',message:'fixture unavailable',retryable:true},request_id:'fixture-list'})});});
   await page.getByRole('searchbox',{name:'搜索项目'}).fill('fixture');await page.waitForTimeout(200);assert.equal(await rows().count(),before);release();await page.getByText('发现记录获取失败',{exact:true}).waitFor();assert.equal(await page.getByText('Aether Labs',{exact:true}).count(),0);
   await page.unroute('**/api/v1/hunter/signals?**');await page.getByRole('button',{name:'重试',exact:true}).click();await loaded();
  });
  await check('1440/390真实页面与右面板无整页横向溢出',async()=>{
   for(const width of [1440,390]){await page.setViewportSize({width,height:1000});await page.reload();await loaded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await page.screenshot({path:path.join(out,'fullwidth-'+width+'.png')});await editor();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await page.screenshot({path:path.join(out,'research-'+width+'.png')});await close();}
  });
  await check('实际Server Action绕过Proxy仍拒匿名/错CSRF，超管真实确认',async()=>{
   const row=(await (await page.request.get(base+'/api/v1/hunter/signals?q=fixture_p110')).json()).data.items.find(item=>item.x_handle==='fixture_p110');
   const anon=await browser.newContext(),anonPage=await anon.newPage();await watch(anonPage);assert.equal(await action(anonPage,row,''),401);await anon.close();
   assert.equal(await action(page,row,'wrong'),403);const me=(await (await page.request.get(base+'/api/v1/auth/me')).json()).data;
   assert.equal(await action(page,row,me.csrf_token),202);await page.goto(base+'/hunter');await loaded();
  });
  await check('user只读、越权拒绝、真实SSE投影及禁用撤销',async()=>{
   const userContext=await browser.newContext({viewport:{width:1440,height:1000}}),userPage=await userContext.newPage();await watch(userPage);await login(userPage,'fixture_reader');
   assert.equal(await userPage.getByRole('button',{name:/猎手管理/}).isDisabled(),true);await userPage.getByRole('button',{name:'研究 / 编辑',exact:true}).first().click();assert.equal(await userPage.getByLabel('项目名称',{exact:true}).isDisabled(),true);
   const write=await userPage.request.post(base+'/api/v1/hunter/accounts',{data:{x_handle:'forged',label:'',notes:'',enabled:true}});assert.equal(write.status(),403);
   const row=(await (await userPage.request.get(base+'/api/v1/hunter/signals?limit=1')).json()).data.items[0],me=(await (await userPage.request.get(base+'/api/v1/auth/me')).json()).data;
   assert.equal(await action(userPage,row,me.csrf_token),403);await userPage.goto(base+'/hunter');await loaded(userPage);
   const frame=await userPage.evaluate(()=>new Promise((resolve,reject)=>{window.__b4_sse_errors=0;const source=new EventSource('/api/v1/events/stream');window.__b4_sse=source;const timer=setTimeout(()=>{source.close();reject(Error('SSE frame deadline'));},8000);source.addEventListener('hunter.discovery.updated',event=>{clearTimeout(timer);resolve(JSON.parse(event.data));});source.onerror=()=>{window.__b4_sse_errors++;};}));
   assert.equal(typeof frame.request_id,'string');assert.ok(frame.data.discovery_id);assert.equal(JSON.stringify(frame).includes('fixture_hunter'),false);
   execFileSync(process.execPath,[path.resolve('integration/tests/provision-browser.mjs'),'disable','fixture_reader'],{env:process.env,stdio:'pipe'});
   await userPage.waitForFunction(()=>window.__b4_sse_errors>0);await userPage.evaluate(()=>window.__b4_sse.close());
   assert.equal((await userPage.request.get(base+'/api/v1/hunter/signals')).status(),401);await userPage.reload();await userPage.waitForURL('**/login?next=*');await userContext.close();
  });
  await check('无脚本异常、第三方请求或演示存储',async()=>{assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.equal(await page.evaluate(()=>localStorage.length),0);});
  fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({status:'passed',passed,errors,external,fixtureOnly:true,actualNext:true,actualB1:true,actualHunterAPI:true,c04:'passed',providerCalls:0},null,2)+'\n');
 }catch(error){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({passed,errors,external,error:String(error)},null,2));console.error(error);process.exitCode=1;}
 finally{await browser.close();}
})();
