const {test,expect}=require('../.tools/node_modules/@playwright/test');
const path=require('node:path');
const artifact=name=>path.join(__dirname,'../evidence/html-v2',name);
const projects=page=>page.locator('.hpv2-projects tbody tr:not([aria-hidden])');
const row=(page,name)=>projects(page).filter({has:page.locator('.hpv2-project-name strong',{hasText:name})});
const dialog=page=>page.getByRole('dialog');
const eventRows=page=>page.locator('.hpv2-events tbody tr:not([aria-hidden])');
async function controls(page){if(!await page.getByLabel('数据模式',{exact:true}).isVisible())await page.locator('.hpv2-demo-settings>summary').click();}
async function add(page,name='UI V2 New Project'){await page.getByRole('button',{name:'＋ 新增项目',exact:true}).click();await dialog(page).getByLabel('项目名称',{exact:true}).fill(name);}
async function log(page){return JSON.parse(await page.getByTestId('callback-log').textContent());}
const audits=new WeakMap();
test.beforeEach(async({page})=>{
  const record={requests:[],errors:[]};audits.set(page,record);page.on('request',request=>record.requests.push(request.url()));page.on('pageerror',error=>record.errors.push(error.message));
  await page.goto('/prototypes/homepage');await expect(projects(page)).toHaveCount(9);
});
test.afterEach(async({page})=>{const record=audits.get(page);expect(record.requests.filter(url=>new URL(url).origin!=='http://127.0.0.1:3700'||new URL(url).pathname.startsWith('/api/'))).toEqual([]);expect(record.errors).toEqual([]);});

test('HTML v2 structure, reference rows, public components and four viewport widths',async({page})=>{
  await expect(page.getByRole('heading',{name:'持续跟踪项目',exact:true})).toHaveCount(1);
  await expect(page.locator('.hpv2-root')).toContainText('演示数据');await expect(page.locator('.hpv2-root')).toContainText('演示参考日期：2026-10-15');
  await expect(page.locator('.ik-shell')).toHaveCount(1);await expect(page.getByRole('navigation',{name:'业务导航'}).getByRole('link')).toHaveCount(3);
  await expect(page.locator('.hp2-overview')).toHaveCount(0);await expect(eventRows(page)).toHaveCount(3);
  expect(await eventRows(page).locator('.hpv2-project-name strong').allTextContents()).toEqual(['Prism Labs','Nova Network','Orbit Network']);
  await expect(eventRows(page).first()).toContainText('3天后');await expect(page.locator('.hpv2-table-footer')).toContainText('1–9 条，共 12 条');
  for(const width of [1440,1920,2560,390]){
    await page.setViewportSize({width,height:width===390?844:1080});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(await page.locator('.hpv2-projects .ik-table td').first().evaluate(e=>getComputedStyle(e).fontSize)).toBe('13px');
    if(width===390)expect(await page.locator('.hpv2-projects .ik-table-scroll').evaluate(e=>e.scrollWidth>e.clientWidth)).toBe(true);
    await page.screenshot({path:artifact(`home-${width}.png`),fullPage:true});
  }
});
test('search name/website/notes, clear/Esc and grade/stage filters are linked to the table',async({page})=>{
  const search=page.getByRole('searchbox',{name:'搜索项目'});await page.keyboard.press('/');await expect(search).toBeFocused();
  await search.fill('papertrade.example');await expect(projects(page)).toHaveCount(1);await expect(row(page,'PaperTrade')).toHaveCount(1);
  await page.keyboard.press('Escape');await expect(projects(page)).toHaveCount(9);
  await search.fill('审计报告');await expect(row(page,'Cobalt Labs')).toHaveCount(1);await page.getByRole('button',{name:'清除搜索项目'}).click();
  await page.locator('.hpv2-grade-filters').getByRole('button',{name:/^S级/}).click();await expect(projects(page)).toHaveCount(3);
  await page.getByLabel('进度筛选',{exact:true}).selectOption('watching');await expect(projects(page)).toHaveCount(2);
  await page.getByRole('button',{name:'清除筛选'}).click();await expect(projects(page)).toHaveCount(9);
});
test('date window follows selected rating and shows only the nearest three explicit events',async({page})=>{
  await page.getByLabel('时间筛选',{exact:true}).selectOption('7');await expect(eventRows(page)).toHaveCount(2);
  await page.locator('.hpv2-grade-filters').getByRole('button',{name:/^A级/}).click();await expect(eventRows(page)).toHaveCount(1);await expect(eventRows(page)).toContainText('Nova Network');
  await page.locator('.hpv2-grade-filters').getByRole('button',{name:/^B级/}).click();await expect(eventRows(page)).toHaveCount(0);await expect(page.locator('.hpv2-events')).toContainText('没有即将到来的重要事件');
  await page.getByLabel('时间筛选',{exact:true}).selectOption('90');await expect(eventRows(page)).toHaveCount(3);
});
test('sort dropdown and table headers change order and announce aria-sort',async({page})=>{
  const names=()=>projects(page).locator('.hpv2-project-name strong').allTextContents();
  expect((await names())[0]).toBe('PaperTrade');await page.getByLabel('表格排序').selectOption('discovered:asc');expect((await names())[0]).toBe('Amber Finance');
  await page.getByLabel('表格排序').selectOption('event:asc');expect((await names())[0]).toBe('Prism Labs');
  await page.getByLabel('表格排序').selectOption('rating:asc');expect((await names()).slice(0,3)).toEqual(['Prism Labs','Vela AI','SixthSense']);
  const nameHeader=page.locator('.hpv2-projects').getByRole('columnheader',{name:'项目名称',exact:true});await nameHeader.getByRole('button').click();await expect(nameHeader).toHaveAttribute('aria-sort','ascending');
  const asc=await names();await nameHeader.getByRole('button').click();await expect(nameHeader).toHaveAttribute('aria-sort','descending');expect((await names())[0]).not.toBe(asc[0]);
});
test('local pagination shows remaining rows and clears selection when changing page',async({page})=>{
  await page.getByLabel('选择Prism Labs',{exact:true}).check();await expect(page.getByRole('button',{name:'移除已选 (1)'})).toBeEnabled();
  await page.getByRole('button',{name:'第 2 页'}).click();await expect(projects(page)).toHaveCount(3);await expect(page.getByRole('button',{name:'移除已选 (0)'})).toBeDisabled();
  await expect(page.getByRole('button',{name:'下一页',exact:true})).toBeDisabled();await page.getByRole('button',{name:'上一页',exact:true}).click();await expect(projects(page)).toHaveCount(9);
});
test('create drawer saves field-only project data and a separate milestone with unknown discovery time',async({page})=>{
  await add(page);await dialog(page).getByLabel('近期重要时间',{exact:true}).fill('2026-10-16');await dialog(page).getByLabel('重要事件',{exact:true}).fill('演示主网上线');
  await dialog(page).getByLabel('备注',{exact:true}).fill('UI V2 note');await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(dialog(page)).toHaveCount(0);
  await page.getByRole('searchbox',{name:'搜索项目'}).fill('UI V2 New Project');await expect(row(page,'UI V2 New Project')).toContainText('未知');
  const call=await log(page);expect(call.name).toBe('create-draft');expect(call.payload.milestone.title).toBe('演示主网上线');expect(call.payload.fields.token_date).toBeNull();expect(call.payload.fields.progress_percent).toBeNull();
  for(const key of ['project_id','discovered_at','home_membership','created_at','updated_at','revision','tenant_id'])expect(call.payload.fields).not.toHaveProperty(key);
});
test('editing changes the independent event and notes without overwriting token date or IDs',async({page})=>{
  await row(page,'Prism Labs').getByRole('button',{name:'编辑',exact:true}).click();await expect(dialog(page).getByLabel('项目名称',{exact:true})).toBeFocused();
  await dialog(page).getByLabel('备注',{exact:true}).fill('V2 updated note');await dialog(page).getByLabel('近期重要时间',{exact:true}).fill('2026-10-16');await dialog(page).getByLabel('重要事件',{exact:true}).fill('独立重要事件');
  await expect(row(page,'Prism Labs')).not.toContainText('V2 updated note');await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(row(page,'Prism Labs')).toContainText('V2 updated note');await expect(eventRows(page).first()).toContainText('独立重要事件');await expect(eventRows(page).first()).toContainText('1天后');
  const call=await log(page);expect(call.payload.target).toEqual({project_id:'demo-reference-1',revision:1});expect(call.payload.draft.fields.token_date).toBe('2026-10-18');expect(call.payload.draft.milestone.date).toBe('2026-10-16');
});
test('single removal confirms completion, keeps data, hides its event and restores previous progress',async({page})=>{
  await row(page,'Prism Labs').getByRole('button',{name:'移除',exact:true}).click();await expect(dialog(page).getByRole('button',{name:'取消',exact:true})).toBeFocused();await expect(dialog(page)).toContainText('监控状态保持原样');await dialog(page).getByRole('button',{name:'取消',exact:true}).click();await expect(row(page,'Prism Labs')).toHaveCount(1);
  await row(page,'Prism Labs').getByRole('button',{name:'移除',exact:true}).click();await dialog(page).getByRole('button',{name:'标记完成并移除'}).click();await expect(page.getByRole('button',{name:'已完成记录 (1)'})).toBeVisible();await expect(eventRows(page).filter({hasText:'Prism Labs'})).toHaveCount(0);
  await page.getByRole('button',{name:'已完成记录 (1)'}).click();await expect(dialog(page)).toContainText('原进度：持续跟踪');await dialog(page).getByRole('button',{name:'恢复跟踪'}).click();await expect(dialog(page)).toContainText('暂无已完成项目');await page.keyboard.press('Escape');await expect(row(page,'Prism Labs')).toContainText('持续跟踪');await expect(eventRows(page).first()).toContainText('Prism Labs');
  expect((await log(page)).name).toBe('restore');
});
test('bulk selection is scoped to visible IDs, supports indeterminate header and one archive callback',async({page})=>{
  await page.getByLabel('全选当前页',{exact:true}).check();await page.getByLabel('选择Prism Labs',{exact:true}).uncheck();
  expect(await page.getByLabel('全选当前页',{exact:true}).evaluate(input=>input.indeterminate)).toBe(true);
  await page.getByRole('button',{name:'移除已选 (8)'}).click();await expect(dialog(page).locator('li')).toHaveCount(8);await dialog(page).getByRole('button',{name:'标记完成并移除'}).click();
  await expect(page.getByRole('button',{name:'已完成记录 (8)'})).toBeVisible();await expect(projects(page)).toHaveCount(4);
  const targets=(await log(page)).payload.targets;expect(targets).toHaveLength(8);expect(new Set(targets.map(target=>target.project_id)).size).toBe(8);expect(targets.every(target=>target.revision===1)).toBe(true);
});
test('dirty drawer cancellation keeps the draft and safe focus before discarding',async({page})=>{
  await add(page);await page.keyboard.press('Escape');await expect(dialog(page)).toContainText('放弃未保存的修改');await expect(dialog(page).getByRole('button',{name:'继续编辑'})).toBeFocused();await dialog(page).getByRole('button',{name:'继续编辑'}).click();await expect(dialog(page).getByLabel('项目名称')).toHaveValue('UI V2 New Project');
  await page.keyboard.press('Escape');await dialog(page).getByRole('button',{name:'放弃修改'}).click();await expect(dialog(page)).toHaveCount(0);await expect(page.getByRole('button',{name:'＋ 新增项目',exact:true})).toBeFocused();
});
test('repeated submit calls once and pending blocks native dialog submit, Esc and close',async({page})=>{
  await add(page);await dialog(page).locator('form').evaluate(form=>{form.requestSubmit();form.requestSubmit();});await expect(dialog(page)).toHaveAttribute('aria-busy','true');await expect(dialog(page).getByRole('button',{name:'关闭弹窗'})).toBeDisabled();await page.keyboard.press('Escape');await expect(dialog(page)).toHaveCount(1);await page.keyboard.press('Tab');expect(await page.evaluate(()=>document.querySelector('dialog').contains(document.activeElement))).toBe(true);
  await expect(dialog(page)).toHaveCount(0);await controls(page);await expect(page.getByLabel('操作回调次数')).toContainText('1');
});
test('readonly and live default capabilities prevent writes and never substitute fixtures',async({page})=>{
  await controls(page);await page.getByLabel('模拟权限').selectOption('user');await expect(page.getByRole('button',{name:'＋ 新增项目',exact:true})).toBeDisabled();await expect(row(page,'Prism Labs').getByRole('button',{name:'编辑',exact:true})).toBeDisabled();await expect(page.getByLabel('全选当前页')).toBeDisabled();
  await row(page,'Prism Labs').locator('.hpv2-project-name').click();await expect(dialog(page)).toContainText('项目 ID');await expect(dialog(page).getByRole('button',{name:'编辑资料'})).toBeDisabled();await page.keyboard.press('Escape');
  await page.getByLabel('数据模式').selectOption('live');await expect(projects(page)).toHaveCount(0);await expect(page.locator('.hpv2-root')).toContainText('AUTH_NOT_CONFIGURED');await expect(page.locator('.hpv2-root')).not.toContainText('Prism Labs');await expect(page.getByRole('button',{name:'＋ 新增项目',exact:true})).toBeDisabled();
});
test('loading/empty/error/refresh retain rows and filters without hiding public error details',async({page})=>{
  await controls(page);await page.getByLabel('列表状态演示').selectOption('loading');await expect(page.locator('.hpv2-projects tbody tr[aria-hidden]')).toHaveCount(5);
  await page.getByLabel('列表状态演示').selectOption('empty');await expect(page.locator('.hpv2-projects')).toContainText('没有符合条件的项目');
  await page.getByLabel('列表状态演示').selectOption('error');await expect(page.locator('.hpv2-projects')).toContainText('UPSTREAM_UNAVAILABLE');await expect(projects(page)).toHaveCount(0);
  await page.getByLabel('列表状态演示').selectOption('ready');await page.getByRole('searchbox',{name:'搜索项目'}).fill('Prism');await page.getByLabel('列表状态演示').selectOption('refreshing');await expect(projects(page)).toHaveCount(1);await expect(page.locator('.hpv2-projects .ik-table-updating')).toBeVisible();
  await page.getByLabel('列表状态演示').selectOption('refresh-error');await expect(row(page,'Prism Labs')).toHaveCount(1);await expect(page.getByRole('searchbox',{name:'搜索项目'})).toHaveValue('Prism');await page.screenshot({path:artifact('refresh-error.png'),fullPage:true});
});
for(const scenario of ['denied','conflict'])test(`${scenario}: public error remains visible and failed data is not applied`,async({page})=>{
  await controls(page);await page.getByLabel('回调结果演示').selectOption(scenario);await add(page);await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(dialog(page)).toContainText(scenario==='denied'?'FORBIDDEN':'VERSION_CONFLICT');await expect(dialog(page)).toContainText('demo-reference-request-1');
  if(scenario==='conflict')await expect(dialog(page).getByRole('button',{name:'保存资料'})).toBeDisabled();await expect(projects(page)).toHaveCount(9);
});
for(const scenario of ['accepted','pending','running','unknown','timeout'])test(`${scenario}: blocks repeat writes and only reconciliation can apply a confirmed result`,async({page})=>{
  await controls(page);await page.getByLabel('回调结果演示').selectOption(scenario);await add(page);await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(dialog(page).getByRole('button',{name:'保存资料'})).toBeDisabled();await expect(dialog(page)).toContainText(scenario==='accepted'?'已受理':scenario==='pending'?'等待执行':scenario==='running'?'操作处理中':'结果待核实');
  await dialog(page).locator('.hpv2-editor-actions').getByRole('button',{name:'关闭',exact:true}).click();await expect(page.getByRole('button',{name:'＋ 新增项目',exact:true})).toBeDisabled();await page.getByLabel('回调结果演示').selectOption('success');await page.getByRole('button',{name:'核对结果'}).click();await expect(page.getByLabel('操作回调次数')).toContainText('2');await page.getByRole('searchbox',{name:'搜索项目'}).fill('UI V2 New Project');await expect(projects(page)).toHaveCount(1);expect((await log(page)).name).toBe('reconcile');
});
test('thrown callback hides private error text and leaves the operation unresolved',async({page})=>{
  await controls(page);await page.getByLabel('回调结果演示').selectOption('throw');await add(page);await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(dialog(page)).toContainText('INTERNAL_ERROR');await expect(dialog(page)).toContainText('结果待核实');await expect(page.locator('body')).not.toContainText('PRIVATE_DEMO_RAW_ERROR');
});
test('drawer fits a phone, traps focus in both directions and restores its trigger',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'＋ 新增项目',exact:true}).click();await expect(dialog(page).getByLabel('项目名称')).toBeFocused();const bounds=await dialog(page).evaluate(e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}));expect(bounds.left).toBeGreaterThanOrEqual(0);expect(bounds.right).toBeLessThanOrEqual(390);
  const close=dialog(page).getByRole('button',{name:'关闭弹窗'});await close.focus();await page.keyboard.press('Shift+Tab');await expect(dialog(page).getByRole('button',{name:'保存资料'})).toBeFocused();await page.keyboard.press('Tab');await expect(close).toBeFocused();await page.screenshot({path:artifact('drawer-mobile.png')});await page.keyboard.press('Escape');await expect(dialog(page)).toHaveCount(0);await expect(page.getByRole('button',{name:'＋ 新增项目',exact:true})).toBeFocused();
});
test('D and null ratings remain editable in other project records without disappearing',async({page})=>{
  await row(page,'Prism Labs').getByRole('button',{name:'编辑',exact:true}).click();await dialog(page).getByLabel('评分',{exact:true}).selectOption('D');await dialog(page).getByRole('button',{name:'保存资料'}).click();await page.getByRole('button',{name:'其他项目 (1)'}).click();await expect(dialog(page)).toContainText('Prism Labs');await expect(dialog(page).locator('.ik-score--d')).toHaveText('D');
  await dialog(page).getByRole('button',{name:'编辑',exact:true}).click();await dialog(page).getByLabel('评分',{exact:true}).selectOption('');await dialog(page).getByRole('button',{name:'保存资料'}).click();await page.getByRole('button',{name:'其他项目 (1)'}).click();await expect(dialog(page)).toContainText('未评分');await dialog(page).getByRole('button',{name:'编辑',exact:true}).click();await dialog(page).getByLabel('评分',{exact:true}).selectOption('A');await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(row(page,'Prism Labs')).toHaveCount(1);
});
test('delete uses a distinct confirmation and preserves progress; record can be joined again',async({page})=>{
  await row(page,'Prism Labs').locator('.hpv2-project-name').click();await dialog(page).getByRole('button',{name:'删除主页条目'}).click();await expect(dialog(page)).toContainText('保留项目资料、ID、进度和监控引用');await expect(dialog(page).getByRole('button',{name:'取消',exact:true})).toBeFocused();await dialog(page).getByRole('button',{name:'确认移除主页'}).click();await page.getByRole('button',{name:'其他项目 (1)'}).click();await dialog(page).getByRole('button',{name:'加入主页'}).click();await page.keyboard.press('Escape');await expect(row(page,'Prism Labs')).toContainText('持续跟踪');
});
test('completion editor follows final HTML: saving completes and archives, restoring returns previous progress',async({page})=>{
  await row(page,'Nova Network').getByRole('button',{name:'编辑',exact:true}).click();await dialog(page).getByLabel('研究进度').selectOption('completed');await expect(dialog(page)).toContainText('保存后移出主页');await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(row(page,'Nova Network')).toHaveCount(0);await expect(page.getByRole('button',{name:'已完成记录 (1)'})).toBeVisible();
  const call=await log(page);expect(call.payload.draft.fields.progress_stage).toBe('completed');expect(call.payload.draft.archive_after_save).toBe(true);
  await page.getByRole('button',{name:'已完成记录 (1)'}).click();await expect(dialog(page)).toContainText('原进度：待开始');await dialog(page).getByRole('button',{name:'恢复跟踪'}).click();await expect(dialog(page)).toContainText('暂无已完成项目');await page.keyboard.press('Escape');await expect(row(page,'Nova Network')).toContainText('待开始');
});
test('demo websites and other-module navigation cannot leave the homepage acceptance scope',async({page})=>{
  await row(page,'Prism Labs').locator('.hpv2-website').click();await expect(page.locator('.hpv2-root')).toContainText('演示官网占位地址');await page.getByRole('navigation',{name:'业务导航'}).getByRole('link',{name:'猎手监控',exact:true}).click();await expect(page).toHaveURL(/prototypes\/homepage$/);
});

test('unknown bulk archive reconciles the original callback once and clears the closed selection',async({page})=>{
  await controls(page);await page.getByLabel('回调结果演示').selectOption('unknown');await page.getByLabel('选择Prism Labs',{exact:true}).check();await page.getByLabel('选择Nova Network',{exact:true}).check();await page.getByRole('button',{name:'移除已选 (2)'}).click();await dialog(page).getByRole('button',{name:'标记完成并移除'}).click();await expect(dialog(page)).toContainText('结果待核实');await expect(dialog(page).getByRole('button',{name:'标记完成并移除'})).toBeDisabled();await dialog(page).getByRole('button',{name:'取消',exact:true}).click();
  await page.getByLabel('回调结果演示').selectOption('success');await page.getByRole('button',{name:'核对结果'}).click();await expect(dialog(page)).toHaveCount(0);await expect(page.getByRole('button',{name:'已完成记录 (2)'})).toBeVisible();await expect(page.getByRole('button',{name:'移除已选 (0)'})).toBeDisabled();await expect(page.getByLabel('操作回调次数')).toContainText('2');
});
test('unknown delete reconciliation closes stale confirmation and preserves original progress',async({page})=>{
  await controls(page);await page.getByLabel('回调结果演示').selectOption('unknown');await row(page,'Prism Labs').locator('.hpv2-project-name').click();await dialog(page).getByRole('button',{name:'删除主页条目'}).click();await dialog(page).getByRole('button',{name:'确认移除主页'}).click();await expect(dialog(page)).toContainText('结果待核实');await dialog(page).getByRole('button',{name:'取消',exact:true}).click();await page.keyboard.press('Escape');await page.getByLabel('回调结果演示').selectOption('success');await page.getByRole('button',{name:'核对结果'}).click();await expect(dialog(page)).toHaveCount(0);await expect(page.getByRole('button',{name:'其他项目 (1)'})).toBeVisible();await expect(page.getByLabel('操作回调次数')).toContainText('2');
  await page.getByRole('button',{name:'其他项目 (1)'}).click();await dialog(page).getByRole('button',{name:'查看资料'}).click();await expect(dialog(page)).toContainText('持续跟踪');
});

test('discovery date composes with search, rating and progress; date-only clear preserves the rest',async({page})=>{
  const date=page.getByLabel('按项目发现日期筛选'),search=page.getByRole('searchbox',{name:'搜索项目'});
  await expect(page.getByRole('button',{name:'全部日期',exact:true})).toBeDisabled();
  await date.fill('2026-10-15');await expect(projects(page)).toHaveCount(1);await expect(row(page,'PaperTrade')).toContainText('10-15 10时');await expect(page.locator('.hpv2-table-footer')).toContainText('发现日期：2026/10/15');
  await page.getByRole('button',{name:/^B级/}).click();await search.fill('激励');await page.getByLabel('进度筛选').selectOption('watching');await expect(row(page,'PaperTrade')).toHaveCount(1);
  await page.getByRole('button',{name:'全部日期',exact:true}).click();await expect(date).toHaveValue('');await expect(search).toHaveValue('激励');await expect(page.getByRole('button',{name:/^B级/})).toHaveAttribute('aria-pressed','true');await expect(page.getByLabel('进度筛选')).toHaveValue('watching');
  await date.fill('2026-10-14');await expect(projects(page)).toHaveCount(0);await expect(page.locator('.hpv2-projects')).toContainText('没有符合条件');
  await page.getByRole('button',{name:'清除筛选',exact:true}).click();await expect(projects(page)).toHaveCount(9);await expect(date).toHaveValue('');await expect(search).toHaveValue('');
});
test('date filter resets pagination and selection, and uses date-specific counts without changing event scope',async({page})=>{
  await page.getByRole('button',{name:'第 2 页'}).click();await page.getByLabel('全选当前页').check();await page.getByLabel('按项目发现日期筛选').fill('2026-10-07');await expect(row(page,'Prism Labs')).toHaveCount(1);await expect(page.getByRole('button',{name:'移除已选 (0)'})).toBeDisabled();await expect(page.getByRole('button',{name:'第 1 页'})).toHaveAttribute('aria-current','page');
  await expect(page.getByRole('button',{name:'全部 (1)',exact:true})).toBeVisible();await expect(eventRows(page)).toHaveCount(3);
  await controls(page);expect(JSON.parse(await page.getByTestId('query-log').textContent()).foundDate).toBe('2026-10-07');await page.getByRole('button',{name:'全部日期',exact:true}).click();expect(JSON.parse(await page.getByTestId('query-log').textContent()).foundDate).toBeNull();
});
test('important hour saves and reopens at midnight and 23, and controls same-day ordering in both lists',async({page})=>{
  async function change(name,hour){await row(page,name).getByRole('button',{name:'编辑',exact:true}).click();await dialog(page).getByLabel('近期重要时间',{exact:true}).fill('2026-10-18');await dialog(page).getByLabel('重要时间：小时',{exact:true}).selectOption(hour);await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(dialog(page)).toHaveCount(0);}
  await change('Prism Labs','23');await change('Nova Network','00');await page.getByLabel('表格排序').selectOption('event:asc');
  expect((await projects(page).locator('.hpv2-project-name strong').allTextContents()).slice(0,2)).toEqual(['Nova Network','Prism Labs']);expect((await eventRows(page).locator('.hpv2-project-name strong').allTextContents()).slice(0,2)).toEqual(['Nova Network','Prism Labs']);
  await expect(row(page,'Prism Labs')).toContainText('10/18 23时');await expect(row(page,'Nova Network')).toContainText('10/18 00时');await expect(eventRows(page).first()).toContainText('10/18 00时');
  await row(page,'Nova Network').getByRole('button',{name:'编辑',exact:true}).click();await expect(dialog(page).getByLabel('重要时间：小时')).toHaveValue('00');await expect(dialog(page).getByLabel('近期重要时间')).toHaveValue('2026-10-18');await page.keyboard.press('Escape');
  await row(page,'Prism Labs').locator('.hpv2-project-name').click();await expect(dialog(page)).toContainText('2026-10-18 23时 · 北京时间');await page.keyboard.press('Escape');await row(page,'Prism Labs').getByRole('button',{name:'编辑',exact:true}).click();await expect(dialog(page).getByLabel('重要时间：小时')).toHaveValue('23');
  expect((await log(page)).payload.draft.milestone.hour).toBe('00');
});
test('clearing an important date saves unknown time and removes its upcoming event without touching the token date',async({page})=>{
  await row(page,'Prism Labs').getByRole('button',{name:'编辑',exact:true}).click();await dialog(page).getByLabel('近期重要时间').fill('');await expect(dialog(page).getByLabel('重要时间：小时')).toBeDisabled();await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(dialog(page)).toHaveCount(0);
  await expect(eventRows(page).filter({hasText:'Prism Labs'})).toHaveCount(0);await expect(row(page,'Prism Labs')).toContainText('未确认');const call=await log(page);expect(call.payload.draft.milestone).toMatchObject({date:null,hour:null,status:'unconfirmed'});expect(call.payload.draft.fields.token_date).toBe('2026-10-18');
});
test('selection follows actual sorted page and is cleared by sort and search changes',async({page})=>{
  await page.getByLabel('表格排序').selectOption('discovered:asc');const visible=await projects(page).locator('.hpv2-project-name').evaluateAll(nodes=>nodes.map(node=>node.dataset.projectId));await page.getByLabel('全选当前页').check();await page.getByRole('button',{name:'移除已选 (9)'}).click();await dialog(page).getByRole('button',{name:'标记完成并移除'}).click();await expect(dialog(page)).toHaveCount(0);expect((await log(page)).payload.targets.map(target=>target.project_id)).toEqual(visible);
  await page.getByLabel('全选当前页').check();await page.getByRole('searchbox',{name:'搜索项目'}).fill('PaperTrade');await expect(page.getByRole('button',{name:'移除已选 (0)'})).toBeDisabled();
});

test('a newly created completed demo project can restore the default pre-save research stage',async({page})=>{
  await add(page,'新建即完成');await dialog(page).getByLabel('研究进度').selectOption('completed');await dialog(page).getByRole('button',{name:'保存资料'}).click();await expect(page.getByRole('button',{name:'已完成记录 (1)'})).toBeVisible();await page.getByRole('button',{name:'已完成记录 (1)'}).click();await expect(dialog(page)).toContainText('原进度：研究中');await dialog(page).getByRole('button',{name:'恢复跟踪'}).click();await expect(dialog(page)).toContainText('暂无已完成项目');await page.keyboard.press('Escape');await expect(dialog(page)).toHaveCount(0);await page.getByRole('searchbox',{name:'搜索项目'}).fill('新建即完成');await expect(row(page,'新建即完成')).toContainText('研究中');
});
