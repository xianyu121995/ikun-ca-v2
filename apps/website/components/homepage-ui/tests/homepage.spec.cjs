const {test,expect}=require('../.tools/node_modules/@playwright/test');
const row=(page,name)=>page.locator('tbody tr').filter({has:page.locator('.hp-project-name strong',{hasText:name})});
test.beforeEach(async({page})=>{await page.goto('/prototypes/homepage');await expect(page.locator('tbody tr')).toHaveCount(12);});

test('demo disclosure, no API/network integration, full-width layouts',async({page})=>{
  const external=[],apis=[],errors=[];
  page.on('request',r=>{if(new URL(r.url()).origin!=='http://127.0.0.1:3700')external.push(r.url());if(new URL(r.url()).pathname.startsWith('/api'))apis.push(r.url());});
  page.on('pageerror',e=>errors.push(e.message));
  await page.reload();await expect(page.locator('tbody tr')).toHaveCount(12);
  await expect(page.getByRole('note')).toContainText('演示数据');
  await expect(page.locator('thead th')).toHaveCount(9);
  await expect(page.locator('.hp-project-name em')).toHaveCount(12);
  for(const width of [1440,1680,2560]){
    await page.setViewportSize({width,height:1050});
    const geometry=await page.evaluate(()=>({page:document.documentElement.scrollWidth,viewport:innerWidth,main:document.querySelector('main').getBoundingClientRect().width,panel:document.querySelector('.hp-project-panel').getBoundingClientRect().width}));
    expect(geometry.page).toBeLessThanOrEqual(width);expect(geometry.panel).toBeGreaterThan(geometry.main*.9);
    await page.screenshot({path:`apps/website/components/homepage-ui/evidence/home-${width}.png`,fullPage:true});
  }
  expect(external).toEqual([]);expect(apis).toEqual([]);expect(errors).toEqual([]);
});

test('search notes, combined filters, sorting and clear empty results',async({page})=>{
  await page.getByRole('textbox',{name:'搜索项目'}).fill('跨链到账');
  await expect(page.locator('tbody tr')).toHaveCount(1);await expect(row(page,'Tide Protocol')).toBeVisible();
  await page.getByRole('button',{name:'清空搜索'}).click();
  await page.getByLabel('评分筛选').selectOption('S');await page.getByLabel('进度筛选').selectOption('进行中');
  await expect(page.locator('tbody tr')).toHaveCount(3);
  await page.getByLabel('分类筛选').selectOption('DeFi');await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('button',{name:'清除筛选',exact:true}).click();
  await page.getByLabel('项目排序').selectOption('discoveredOn:desc');await expect(page.locator('tbody tr').first()).toContainText('Echo Identity');
  await page.getByLabel('项目排序').selectOption('progress:desc');await expect(page.locator('tbody tr').first()).toContainText('Flux Garden');
  await page.getByRole('button',{name:'发现时间',exact:true}).click();await expect(page.locator('tbody tr').first()).toContainText('Echo Identity');
  await page.getByRole('button',{name:'发现时间',exact:true}).click();await expect(page.locator('tbody tr').first()).toContainText('Cobalt Play');
  await page.getByRole('textbox',{name:'搜索项目'}).fill('no-such-project');await expect(page.getByRole('heading',{name:'没有匹配的项目'})).toBeVisible();
  await page.locator('.hp-empty').getByRole('button',{name:'清除筛选'}).click();await expect(page.locator('tbody tr')).toHaveCount(12);
});

test('project drawer, website placeholder, save and browser persistence',async({page})=>{
  await row(page,'Orbit Layer').locator('.hp-project-name').click();
  await expect(page.getByRole('dialog',{name:'项目资料'})).toBeVisible();
  await expect(page.locator('.hp-detail-body')).toContainText('UI 演示内容');
  await page.screenshot({path:'apps/website/components/homepage-ui/evidence/project-drawer.png'});
  await page.locator('.hp-detail-body .hp-website').click();await expect(page.getByRole('status')).toContainText('演示官网占位地址');
  await page.getByRole('button',{name:'编辑资料',exact:true}).click();
  await page.getByLabel('备注 / 下一步', {exact:true}).fill('浏览器验收：下周检查任务清单');
  await page.getByRole('button',{name:'保存修改'}).click();
  await page.keyboard.press('Escape');await expect(row(page,'Orbit Layer')).toContainText('浏览器验收：下周检查任务清单');
  await page.reload();await expect(row(page,'Orbit Layer')).toContainText('浏览器验收：下周检查任务清单');
});

test('add project, reject duplicate, discard dirty changes, local delete confirmation',async({page})=>{
  await page.getByRole('button',{name:'添加项目',exact:true}).click();
  await page.getByLabel('项目名称',{exact:false}).fill('Orbit Layer');
  await page.getByRole('button',{name:'添加演示项目',exact:true}).click();await expect(page.locator('.hp-form-error')).toContainText('已有同名项目');
  await page.getByLabel('项目名称',{exact:false}).fill('UI Test Project');
  await page.getByLabel('官网',{exact:true}).fill('https://ui-test.example');
  await page.getByLabel('评分',{exact:true}).selectOption('A');
  await page.getByLabel('完成比例（%）').fill('45');
  await page.getByRole('button',{name:'添加演示项目',exact:true}).click();await expect(page.locator('tbody tr')).toHaveCount(13);
  await row(page,'UI Test Project').getByRole('button',{name:'编辑 UI Test Project',exact:true}).click();
  await page.getByLabel('项目简介',{exact:true}).fill('未保存的文字');
  await page.keyboard.press('Escape');await expect(page.getByRole('heading',{name:'放弃未保存的修改？'})).toBeVisible();
  await page.getByRole('button',{name:'继续编辑'}).click();await expect(page.getByLabel('项目简介',{exact:true})).toHaveValue('未保存的文字');
  await page.getByRole('button',{name:'取消',exact:true}).click();await page.getByRole('button',{name:'放弃修改'}).click();
  await row(page,'UI Test Project').getByRole('button',{name:'更多操作 UI Test Project',exact:true}).click();await page.getByRole('button',{name:'删除项目',exact:true}).click();
  await expect(page.getByRole('button',{name:'确认删除'})).toBeDisabled();await page.getByLabel('删除确认文字').fill('删除');
  await page.screenshot({path:'apps/website/components/homepage-ui/evidence/delete-confirm.png'});
  await page.getByRole('button',{name:'确认删除'}).click();await expect(row(page,'UI Test Project')).toHaveCount(0);await expect(page.locator('tbody tr')).toHaveCount(12);
});

test('batch remove, removed list, restoration and undo',async({page})=>{
  await row(page,'Orbit Layer').getByRole('checkbox').check();await row(page,'Velum Finance').getByRole('checkbox').check();
  await page.getByRole('button',{name:'从主页移除',exact:true}).click();await page.getByRole('button',{name:'确认移除'}).click();
  await expect(page.locator('tbody tr')).toHaveCount(10);await page.getByRole('button',{name:'撤销',exact:true}).click();await expect(page.locator('tbody tr')).toHaveCount(12);
  await row(page,'Orbit Layer').getByRole('checkbox').check();await page.getByRole('button',{name:'从主页移除',exact:true}).click();await page.getByRole('button',{name:'确认移除'}).click();
  await page.getByRole('tab',{name:'已移除'}).click();await expect(page.locator('tbody tr')).toHaveCount(3);
  await row(page,'Orbit Layer').getByRole('button',{name:'更多操作 Orbit Layer',exact:true}).click();await page.getByRole('button',{name:'重新加入主页',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(2);await page.getByRole('tab',{name:'正在做'}).click();await expect(row(page,'Orbit Layer')).toBeVisible();
});

test('filter-scoped select all, density and keyboard',async({page})=>{
  await page.keyboard.press('/');await expect(page.getByRole('textbox',{name:'搜索项目'})).toBeFocused();
  await page.getByLabel('评分筛选').selectOption('A');await page.getByRole('checkbox',{name:'选择当前筛选的全部项目'}).check();
  await expect(page.locator('.hp-context-bar')).toContainText('已选择 4 个项目');await page.getByRole('button',{name:'取消选择'}).click();
  await page.getByRole('button',{name:'切换舒适行高'}).click();await expect(page.locator('.hp-table-scroll')).not.toHaveClass(/compact/);
});

test('cross-tab synchronization and corrupt local storage recovery',async({page,context})=>{
  const other=await context.newPage();await other.goto('/prototypes/homepage');await expect(other.locator('tbody tr')).toHaveCount(12);
  await page.getByRole('button',{name:'编辑 Orbit Layer',exact:true}).click();await page.getByLabel('备注 / 下一步',{exact:true}).fill('跨标签页同步验证');await page.getByRole('button',{name:'保存修改'}).click();
  await expect(row(other,'Orbit Layer')).toContainText('跨标签页同步验证');await other.close();
  await page.evaluate(()=>localStorage.setItem('ikun:v2:homepage-ui:demo:v1','not-json'));
  await page.reload();await expect(page.locator('.hp-storage-error')).toContainText('演示存储无法读取');
  await page.getByRole('note').getByRole('button',{name:'重置演示'}).click();await page.getByRole('dialog').getByRole('button',{name:'重置演示',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(12);await expect(page.locator('.hp-storage-error')).toHaveCount(0);
});

test('mobile: contained horizontal table and accessible dialogs',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
  await expect(page.locator('.hp-table-scroll')).toBeVisible();
  await page.screenshot({path:'apps/website/components/homepage-ui/evidence/home-mobile.png',fullPage:true});
  await page.getByRole('button',{name:'添加项目',exact:true}).click();await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByLabel('项目名称',{exact:false})).toBeFocused();
  await page.screenshot({path:'apps/website/components/homepage-ui/evidence/add-project-mobile.png'});
  await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('explicit read-only UI preview prevents local writes while allowing detail and search',async({page})=>{
  await page.getByLabel('界面权限演示').selectOption('user');
  await expect(page.getByRole('button',{name:'添加项目',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'编辑 Orbit Layer',exact:true})).toBeDisabled();
  await expect(page.getByRole('checkbox',{name:'选择 Orbit Layer',exact:true})).toBeDisabled();
  await expect(page.getByRole('note').getByRole('button',{name:'重置演示'})).toBeDisabled();
  await row(page,'Orbit Layer').locator('.hp-project-name').click();
  await expect(page.getByRole('dialog',{name:'项目资料'})).toBeVisible();
  await expect(page.getByRole('button',{name:'编辑资料',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'从主页移除',exact:true})).toBeDisabled();
  await page.screenshot({path:'apps/website/components/homepage-ui/evidence/read-only-drawer.png'});
  await page.keyboard.press('Escape');
  await page.getByRole('textbox',{name:'搜索项目'}).fill('Orbit');await expect(page.locator('tbody tr')).toHaveCount(1);
  expect(await page.evaluate(()=>localStorage.getItem('ikun:v2:homepage-ui:demo:v1'))).toBeNull();
});

test('switching to read-only removes previously offered mutation actions',async({page})=>{
  await row(page,'Orbit Layer').getByRole('checkbox').check();
  await page.getByRole('button',{name:'从主页移除',exact:true}).click();
  await page.getByRole('button',{name:'确认移除'}).click();
  await expect(page.getByRole('button',{name:'撤销',exact:true})).toBeVisible();
  const before=await page.evaluate(()=>localStorage.getItem('ikun:v2:homepage-ui:demo:v1'));
  await page.getByLabel('界面权限演示').selectOption('user');
  await expect(page.getByRole('button',{name:'撤销',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'添加项目',exact:true})).toBeDisabled();
  expect(await page.evaluate(()=>localStorage.getItem('ikun:v2:homepage-ui:demo:v1'))).toBe(before);
});
