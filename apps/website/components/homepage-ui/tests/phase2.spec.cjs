const {test,expect}=require('../.tools/node_modules/@playwright/test');
const path=require('node:path');
const artifact=name=>path.join(__dirname,'../evidence/phase2',name);
const row=(page,name)=>page.locator('tbody tr').filter({has:page.locator('.hp2-project-name strong',{hasText:name})});
const dialog=page=>page.getByRole('dialog');
const add=async page=>{await page.getByRole('button',{name:'添加项目',exact:true}).click();await dialog(page).getByLabel('项目名称',{exact:true}).fill('UI0 New Project');};
test.beforeEach(async({page})=>{await page.goto('/prototypes/homepage');await expect(page.locator('tbody tr')).toHaveCount(10);});

test('DTO display, scoped demo labels, unknown data and required width matrix',async({page})=>{
  const requests=[],errors=[];page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(e.message));
  await page.reload();await expect(page.locator('tbody tr')).toHaveCount(10);
  await expect(page.locator('.hp2-mode')).toContainText('演示数据');await expect(page.locator('.hp2-scope')).toContainText('ikun-main');
  await expect(row(page,'Morrow Labs')).toContainText('D');await expect(row(page,'Flux Garden')).toContainText('未评分');
  await expect(row(page,'Nexa Compute')).toContainText('未知');await expect(row(page,'Orbit Layer')).toContainText('2026-10-01 10:30');
  await expect(row(page,'Nexa Compute').locator('.hp2-progress>div')).toHaveCount(0);
  for(const width of [1440,1920,2560,390]){
    await page.setViewportSize({width,height:width===390?844:1080});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);
    expect(await page.locator('.hp2-table').evaluate(e=>getComputedStyle(e.querySelector('td')).fontSize)).toBe('13px');
    if(width===390)expect(await page.locator('.hp2-table-scroll').evaluate(e=>e.scrollWidth>e.clientWidth)).toBe(true);
    await page.screenshot({path:artifact(`home-${width}.png`),fullPage:true});
  }
  expect(requests.filter(url=>new URL(url).origin!=='http://127.0.0.1:3700'||new URL(url).pathname.startsWith('/api/'))).toEqual([]);expect(errors).toEqual([]);
});
test('search Esc/clear, D/null rating, progress, membership and opaque cursor callbacks',async({page})=>{
  await page.keyboard.press('/');await expect(page.getByRole('textbox',{name:'搜索项目'})).toBeFocused();
  await page.getByRole('textbox',{name:'搜索项目'}).fill('Orbit');await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.keyboard.press('Escape');await expect(page.getByRole('textbox',{name:'搜索项目'})).toHaveValue('');
  await page.getByLabel('评分筛选').selectOption('D');await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByLabel('评分筛选').selectOption('unrated');await expect(page.locator('tbody tr')).toHaveCount(2);
  await page.getByLabel('进度筛选').selectOption('todo');await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.getByTestId('query-log')).toContainText('unrated');await page.getByRole('button',{name:'清除筛选'}).click();
  await page.getByRole('tab',{name:'未加入主页'}).click();await expect(row(page,'Nova Bridge')).toHaveCount(1);
  await page.getByRole('tab',{name:'正在做'}).click();await page.getByLabel('列表状态演示').selectOption('page');
  await page.getByRole('button',{name:'下一页'}).click();await expect(page.getByTestId('callback-log')).toContainText('demo-next-cursor');
});
test('loading/empty/error/refresh retain old rows and filters without demo fallback',async({page})=>{
  await page.getByLabel('列表状态演示').selectOption('loading');await expect(page.getByRole('status',{name:'正在加载项目'})).toBeVisible();await expect(page.locator('tbody tr')).toHaveCount(0);
  await page.getByLabel('列表状态演示').selectOption('empty');await expect(page.getByRole('heading',{name:'主页还没有项目'})).toBeVisible();
  await page.getByLabel('列表状态演示').selectOption('error');await expect(page.locator('.hp2-error-row')).toContainText('UPSTREAM_UNAVAILABLE');await expect(page.locator('tbody tr')).toHaveCount(0);
  await page.getByLabel('列表状态演示').selectOption('ready');await page.getByRole('textbox',{name:'搜索项目'}).fill('Orbit');
  await page.getByLabel('列表状态演示').selectOption('refreshing');await expect(page.locator('tbody tr')).toHaveCount(1);await expect(page.locator('.hp2-refreshing')).toContainText('保留');
  await page.getByLabel('列表状态演示').selectOption('refresh-error');await expect(row(page,'Orbit Layer')).toHaveCount(1);await expect(page.getByRole('textbox',{name:'搜索项目'})).toHaveValue('Orbit');
  await page.screenshot({path:artifact('refresh-error.png'),fullPage:true});
});
test('create emits field-only payload with null values; data changes only after success callback',async({page})=>{
  await add(page);await dialog(page).getByLabel('评分',{exact:true}).selectOption('D');
  await dialog(page).getByRole('button',{name:'添加项目',exact:true}).click();
  await expect(dialog(page)).toHaveCount(0);await expect(row(page,'UI0 New Project')).toContainText('未知');
  const payload=JSON.parse(await page.getByTestId('callback-log').textContent()).payload;
  expect(payload.rating).toBe('D');expect(payload.progress_percent).toBeNull();expect(payload.token_date).toBeNull();expect(payload.category).toBeNull();
  for(const key of ['project_id','tenant_id','discovered_at','home_membership','created_at','updated_at','role'])expect(payload).not.toHaveProperty(key);
  expect(await row(page,'UI0 New Project').getAttribute('data-project-id')).toMatch(/^demo-created-/);
});
test('editing preserves immutable IDs/times and emits revision; dirty cancellation protects draft',async({page})=>{
  await page.getByRole('button',{name:'编辑 Orbit Layer',exact:true}).click();await expect(dialog(page)).toContainText('发现时间和服务端 ID/时间只读');
  await dialog(page).getByLabel('备注 / 下一步',{exact:true}).fill('UI0 updated note');await page.keyboard.press('Escape');
  await expect(dialog(page)).toContainText('放弃未保存的修改');await dialog(page).getByRole('button',{name:'继续编辑'}).click();
  await dialog(page).getByRole('button',{name:'保存修改'}).click();await expect(row(page,'Orbit Layer')).toContainText('UI0 updated note');
  const call=JSON.parse(await page.getByTestId('callback-log').textContent());expect(call.payload.target).toEqual({project_id:'demo-phase2-1',revision:1});
  expect(call.payload.fields).not.toHaveProperty('discovered_at');expect(call.payload.fields).not.toHaveProperty('home_membership');
});
test('home remove and delete preserve records, stage and monitoring references; cancel initially focused',async({page})=>{
  await row(page,'Orbit Layer').getByRole('button',{name:'移除',exact:true}).click();
  await expect(dialog(page)).toContainText('监控状态保持原样');await expect(dialog(page).getByRole('button',{name:'取消',exact:true})).toBeFocused();
  await dialog(page).getByRole('button',{name:'确认移除主页'}).click();await page.getByRole('tab',{name:'已移除'}).click();await expect(row(page,'Orbit Layer')).toContainText('72%');
  await row(page,'Orbit Layer').getByRole('button',{name:'加入',exact:true}).click();await dialog(page).getByRole('button',{name:'确认加入'}).click();
  await page.getByRole('tab',{name:'正在做'}).click();await row(page,'Orbit Layer').locator('.hp2-project-name').click();await dialog(page).getByRole('button',{name:'删除主页条目'}).click();
  await dialog(page).getByRole('button',{name:'确认移除主页'}).click();await expect(page.getByTestId('callback-log')).toContainText('delete');
  await page.getByRole('tab',{name:'已移除'}).click();await expect(row(page,'Orbit Layer')).toContainText('72%');await expect(row(page,'Orbit Layer')).toContainText('参与中');
});
test('user cannot execute writes; live defaults capability=false and never falls back to fixtures',async({page})=>{
  await page.getByLabel('模拟权限').selectOption('user');await expect(page.getByRole('button',{name:'添加项目',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'编辑 Orbit Layer',exact:true})).toBeDisabled();
  await row(page,'Orbit Layer').locator('.hp2-project-name').click();await expect(dialog(page)).toContainText('项目 ID');await expect(dialog(page).getByRole('button',{name:'编辑资料'})).toBeDisabled();await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'O Orbit Layer 基础设施 演示'})).toBeFocused();
  await page.getByLabel('数据模式').selectOption('live');await expect(page.locator('.hp2-root')).toHaveAttribute('data-mode','live');
  await expect(page.locator('tbody tr')).toHaveCount(0);await expect(page.locator('.hp2-error-row')).toContainText('AUTH_NOT_CONFIGURED');await expect(page.getByRole('button',{name:'添加项目',exact:true})).toBeDisabled();
  await expect(page.getByLabel('操作回调次数')).toContainText('0');await expect(page.locator('body')).not.toContainText('Orbit Layer');
});
for(const scenario of ['denied','conflict'])test(`${scenario}: public callback error/request_id visible without success`,async({page})=>{
  await page.getByLabel('回调结果演示').selectOption(scenario);await add(page);await dialog(page).getByRole('button',{name:'添加项目',exact:true}).click();
  await expect(dialog(page)).toContainText(scenario==='denied'?'FORBIDDEN':'VERSION_CONFLICT');await expect(dialog(page)).toContainText('demo-request-1');
  await expect(row(page,'UI0 New Project')).toHaveCount(0);await expect(page.getByLabel('操作回调次数')).toContainText('1');
  if(scenario==='conflict'){await expect(dialog(page).getByRole('button',{name:'添加项目',exact:true})).toBeDisabled();await page.keyboard.press('Escape');await expect(dialog(page)).toContainText('放弃未保存的修改');await expect(dialog(page).getByRole('button',{name:'继续编辑'})).toBeFocused();}
});
test('rapid repeated submits call once, pending blocks Esc and close, focus restores on completion',async({page})=>{
  await add(page);await dialog(page).locator('form').evaluate(form=>{form.requestSubmit();form.requestSubmit();});
  await expect(dialog(page)).toHaveAttribute('aria-busy','true');await expect(dialog(page).getByRole('button',{name:'关闭',exact:true})).toBeDisabled();
  await page.keyboard.press('Escape');await expect(dialog(page)).toHaveCount(1);await page.keyboard.press('Tab');
  expect(await page.evaluate(()=>document.querySelector('dialog').contains(document.activeElement))).toBe(true);
  await expect(dialog(page)).toHaveCount(0);await expect(page.getByLabel('操作回调次数')).toContainText('1');await expect(page.getByRole('button',{name:'添加项目',exact:true})).toBeFocused();
});
for(const scenario of ['accepted','pending','unknown','timeout'])test(`${scenario}: no false success, no repeat write; reconciliation uses separate callback`,async({page})=>{
  await page.getByLabel('回调结果演示').selectOption(scenario);await add(page);await dialog(page).getByRole('button',{name:'添加项目',exact:true}).click();
  await expect(dialog(page)).toContainText(scenario==='accepted'?'已受理':scenario==='pending'?'等待执行':'结果待核实');
  await expect(dialog(page).getByRole('button',{name:'添加项目',exact:true})).toBeDisabled();await expect(row(page,'UI0 New Project')).toHaveCount(0);
  await dialog(page).locator('.hp2-dialog-footer').getByRole('button',{name:'关闭',exact:true}).click();await expect(page.getByRole('button',{name:'添加项目',exact:true})).toBeDisabled();
  await page.getByLabel('回调结果演示').selectOption('success');await page.getByRole('button',{name:'核对结果'}).click();
  await expect(page.getByTestId('callback-log')).toContainText('reconcile');await expect(page.getByLabel('操作回调次数')).toContainText('2');await expect(row(page,'UI0 New Project')).toHaveCount(1);
});
test('rejected callback hides raw exception and leaves outcome unknown',async({page})=>{
  await page.getByLabel('回调结果演示').selectOption('throw');await add(page);await dialog(page).getByRole('button',{name:'添加项目',exact:true}).click();
  await expect(dialog(page)).toContainText('结果待核实');await expect(dialog(page)).toContainText('INTERNAL_ERROR');await expect(page.locator('body')).not.toContainText('PRIVATE_DEMO_RAW_ERROR');
});
test('dialog focus wraps both ways, mobile form fits, closes with Esc and restores trigger',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'添加项目',exact:true}).click();await expect(dialog(page).getByLabel('项目名称')).toBeFocused();
  const close=dialog(page).getByRole('button',{name:'关闭',exact:true});await close.focus();await page.keyboard.press('Shift+Tab');await expect(dialog(page).getByRole('button',{name:'添加项目',exact:true})).toBeFocused();
  await page.keyboard.press('Tab');await expect(close).toBeFocused();await page.screenshot({path:artifact('mobile-editor.png')});
  await page.keyboard.press('Escape');await expect(dialog(page)).toHaveCount(0);await expect(page.getByRole('button',{name:'添加项目',exact:true})).toBeFocused();
});
