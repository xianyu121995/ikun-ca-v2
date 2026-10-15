const {test,expect}=require('../.tools/node_modules/@playwright/test');
const path=require('node:path');
const rows=page=>page.locator('#rows tr').filter({has:page.locator('input.check')});
const row=(page,name)=>rows(page).filter({has:page.locator('.name',{hasText:name})});
const drawer=page=>page.locator('#drawer');
const archive=page=>page.locator('#archiveBack');
const audits=new WeakMap();
test.beforeEach(async({page})=>{const audit={requests:[],errors:[]};audits.set(page,audit);page.on('request',r=>audit.requests.push(r.url()));page.on('pageerror',e=>audit.errors.push(e.message));await page.goto('/prototypes/homepage/html');await expect(rows(page)).toHaveCount(9);});
test.afterEach(async({page})=>{const audit=audits.get(page);expect(audit.errors).toEqual([]);expect(audit.requests.filter(url=>new URL(url).origin!=='http://127.0.0.1:3700'||new URL(url).pathname.startsWith('/api/'))).toEqual([]);});
test('final design retains its original dark layout, compact grades, three events and demo labels',async({page})=>{
  await expect(page.getByRole('heading',{name:'持续跟踪项目',exact:true})).toHaveCount(1);await expect(page.locator('#events tr')).toHaveCount(3);await expect(page.locator('#events tr').first()).toContainText('10/18 14时');await expect(page.locator('footer')).toContainText('未接 projects.db');
  expect(await page.locator('#rows .grade').first().evaluate(e=>e.getBoundingClientRect().height)).toBeLessThanOrEqual(28);
  await page.screenshot({path:path.join(__dirname,'../evidence/html-v2/final-html-1920.png'),fullPage:true});
});
test('calendar, rating and search combine; date clear preserves both filters',async({page})=>{
  await page.getByLabel('按项目发现日期筛选').fill('2026-10-15');await expect(row(page,'PaperTrade')).toHaveCount(1);await expect(page.locator('#trackingCount')).toHaveText('(1)');await page.locator('[data-grade="B"]').click();await page.getByLabel('搜索项目').fill('激励');await expect(rows(page)).toHaveCount(1);
  await page.getByRole('button',{name:'全部日期',exact:true}).click();await expect(page.getByLabel('搜索项目')).toHaveValue('激励');await expect(page.locator('[data-grade="B"]')).toHaveClass(/selected/);await expect(rows(page)).toHaveCount(1);
  await page.getByLabel('按项目发现日期筛选').fill('2026-10-14');await expect(rows(page)).toHaveCount(0);await expect(page.getByLabel('全选',{exact:true})).toBeDisabled();
});
test('sorted current-page selection removes exactly the visible projects and restore keeps original progress',async({page})=>{
  await page.getByLabel('表格排序').selectOption('old');const names=await rows(page).locator('.name').allTextContents();await page.getByLabel('全选',{exact:true}).check();await page.getByRole('button',{name:'移除已选 (9)'}).click();await expect(page.locator('#dialogBack button').first()).toBeFocused();await page.locator('#confirmBtn').click();await expect(rows(page)).toHaveCount(3);
  await page.getByRole('button',{name:/已完成记录/}).click();expect(await archive(page).locator('.archive-name').allTextContents()).toEqual(expect.arrayContaining(names));await expect(archive(page).locator('.archive-name')).toHaveCount(9);await archive(page).getByRole('button',{name:'恢复跟踪'}).first().click();await expect(archive(page).locator('.archive-name')).toHaveCount(8);await page.keyboard.press('Escape');await expect(archive(page)).toHaveAttribute('aria-hidden','true');
});
test('search, sort, grade, date and page transitions clear stale selections; header supports partial selection',async({page})=>{
  await page.getByLabel('选择Prism Labs',{exact:true}).check();expect(await page.getByLabel('全选',{exact:true}).evaluate(e=>e.indeterminate)).toBe(true);await page.getByRole('button',{name:'下一页',exact:true}).click();await expect(rows(page)).toHaveCount(3);await expect(page.locator('#bulkBtn')).toHaveText('移除已选 (0)');
  await page.getByLabel('全选',{exact:true}).check();await page.getByLabel('搜索项目').fill('Prism');await expect(page.locator('#bulkBtn')).toBeDisabled();await page.getByLabel('搜索项目').fill('');await page.getByLabel('全选',{exact:true}).check();await page.getByLabel('表格排序').selectOption('event');await expect(page.locator('#bulkBtn')).toBeDisabled();
});
test('hour changes save, reopen and sort on the same date including midnight and 23',async({page})=>{
  for(const [name,hour] of [['Prism Labs','23'],['Nova Network','00']]){await row(page,name).getByRole('button',{name:'编辑',exact:true}).click();await page.getByLabel('重要日期').fill('2026-10-18');await page.getByLabel('重要时间：小时').selectOption(hour);await page.getByRole('button',{name:'保存资料',exact:true}).click();await expect(drawer(page)).toHaveAttribute('aria-hidden','true');}
  await page.getByLabel('表格排序').selectOption('event');expect((await rows(page).locator('.name').allTextContents()).slice(0,2)).toEqual(['Nova Network','Prism Labs']);await expect(row(page,'Nova Network')).toContainText('10/18 00时');await expect(page.locator('#events tr').first()).toContainText('10/18 00时');
  await row(page,'Prism Labs').getByRole('button',{name:'编辑',exact:true}).click();await expect(page.getByLabel('重要时间：小时')).toHaveValue('23');await expect(page.getByLabel('重要日期')).toHaveValue('2026-10-18');await page.keyboard.press('Escape');
});
test('create, edit, remove, completion editor and restore preserve records and pre-completion progress',async({page})=>{
  await page.getByRole('button',{name:'＋ 新增项目'}).click();await page.getByRole('button',{name:'保存资料',exact:true}).click();await expect(page.locator('#toast')).toHaveText('请填写项目名称');await page.getByLabel('项目名称',{exact:true}).fill('验收演示项目');await page.getByLabel('研究进度').selectOption('测试进行中');await page.getByLabel('重要日期').fill('2026-10-16');await page.getByLabel('重要事件').fill('验收演示事件');await page.getByLabel('重要时间：小时').selectOption('09');await page.getByRole('button',{name:'保存资料',exact:true}).click();
  await page.getByLabel('搜索项目').fill('验收演示项目');await expect(rows(page)).toHaveCount(1);await row(page,'验收演示项目').getByRole('button',{name:'编辑',exact:true}).click();await page.getByLabel('研究进度').selectOption('已完成');await page.getByRole('button',{name:'保存资料',exact:true}).click();await expect(rows(page)).toHaveCount(0);await page.getByRole('button',{name:/已完成记录/}).click();await expect(archive(page)).toContainText('原进度：测试进行中');await archive(page).getByRole('button',{name:'恢复跟踪'}).click();await page.getByRole('button',{name:'关闭已完成记录'}).click();await expect(row(page,'验收演示项目')).toContainText('测试进行中');
  await row(page,'验收演示项目').getByRole('button',{name:'移除',exact:true}).click();await page.locator('#dialogBack').getByRole('button',{name:'取消',exact:true}).click();await expect(rows(page)).toHaveCount(1);await row(page,'验收演示项目').getByRole('button',{name:'移除',exact:true}).click();await page.locator('#confirmBtn').click();await expect(rows(page)).toHaveCount(0);
});
test('invalid website is rejected, demo links stay in scope, and drawer cancel, close and focus trap work',async({page})=>{
  await row(page,'Prism Labs').getByRole('button',{name:'编辑',exact:true}).click();await expect(page.getByLabel('项目名称',{exact:true})).toBeFocused();await page.getByLabel('官网',{exact:true}).fill('javascript:alert(1)');await page.getByRole('button',{name:'保存资料',exact:true}).click();await expect(page.locator('#toast')).toContainText('http 或 https');await expect(drawer(page)).toHaveAttribute('aria-hidden','false');
  await page.getByRole('button',{name:'关闭项目编辑'}).focus();await page.keyboard.press('Shift+Tab');await expect(page.getByRole('button',{name:'保存资料',exact:true})).toBeFocused();await page.keyboard.press('Tab');await expect(page.getByRole('button',{name:'关闭项目编辑'})).toBeFocused();await page.getByRole('button',{name:'取消',exact:true}).click();await expect(row(page,'Prism Labs').getByRole('button',{name:'编辑',exact:true})).toBeFocused();await row(page,'Prism Labs').locator('.web-link').click();await expect(page.locator('#toast')).toHaveText('演示官网占位地址');
  await page.locator('.navlink').nth(1).click();await expect(page.locator('#toast')).toContainText('本窗口只演示主页');
});
test('event windows and all grade buttons work, and archive close controls stay usable',async({page})=>{
  for(const value of ['7','30','90','all']){await page.getByLabel('时间筛选').selectOption(value);await expect(page.locator('#events tr')).toHaveCount(value==='7'?2:3);}
  for(const grade of ['S','A','B','all']){await page.locator(`[data-grade="${grade}"]`).click();await expect(page.locator(`[data-grade="${grade}"]`)).toHaveClass(/selected/);expect(await rows(page).count()).toBeGreaterThan(0);}
  await page.getByRole('button',{name:/已完成记录/}).click();await expect(archive(page)).toContainText('暂无已完成项目');await archive(page).getByRole('button',{name:'关闭',exact:true}).click();await expect(archive(page)).toHaveAttribute('aria-hidden','true');
});
