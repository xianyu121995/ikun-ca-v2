import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.UI0_URL || 'http://127.0.0.1:3900';
if (!['127.0.0.1', 'localhost'].includes(new URL(base).hostname)) throw new Error('Local UI only');
const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1080 }, timezoneId: 'Asia/Shanghai', reducedMotion: 'reduce' });
const page = await context.newPage(); page.setDefaultTimeout(8000);
const results = [], errors = [], violations = [], directory = new URL('../evidence/', import.meta.url);
await mkdir(directory, { recursive: true });
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => { const url = new URL(request.url()); if (url.origin !== new URL(base).origin || /^\/(api|internal)\//.test(url.pathname)) violations.push(request.url()); });
page.on('websocket', socket => { if (!socket.url().includes('/_next/')) violations.push(socket.url()); });
const cards = () => page.locator('[data-post]');
const manager = () => page.getByRole('dialog', { name: '监控账号管理', exact: true });
const modal = () => page.getByRole('dialog', { name: '确认删除账号？', exact: true });
const text = async (locator, value) => locator.filter({ hasText: value }).waitFor();
const demo = async () => { await page.goto(`${base}/tracking?mode=demo`); await page.waitForFunction(() => document.querySelectorAll('[data-post]').length === 6); };
const openManager = async () => { await page.getByRole('button', { name: /^监控账号总数/ }).click(); await manager().waitFor(); };
const form = async (handle = '@demo_project', name = 'Demo Project', note = '重点关注测试网上线') => {
  await manager().getByLabel(/^X 用户名/).fill(handle);
  await manager().getByLabel(/^项目名称/).fill(name);
  await manager().getByLabel(/^备注（优先显示）/).fill(note);
};
async function check(name, run) { try { await run(); results.push({ name, passed: true }); console.log(`PASS ${name}`); } catch (error) { results.push({ name, passed: false, error: error.message }); throw error; } }
try {
  await check('default is empty readonly with no fixture or fabricated identity', async () => {
    await page.goto(`${base}/tracking`); await page.getByRole('heading', { name: '猎手项目追踪', exact: true }).waitFor();
    assert.equal(await cards().count(), 0); assert.equal(await page.getByRole('button', { name: '刷新', exact: true }).isDisabled(), true);
    await openManager(); assert.equal(await manager().getByRole('button', { name: /添加|删除/ }).count(), 0);
    await page.keyboard.press('Escape'); assert.deepEqual(await context.cookies(), []);
  });
  await check('approved structure: five stats, six vertical posts, no rail or added tools', async () => {
    await demo(); assert.equal(await page.getByTestId('account-count').innerText(), '10');
    assert.equal(await cards().count(), 6); assert.equal(await page.locator('.ik-shell').count(), 1); assert.equal(await page.locator('.ik-nav-link').count(), 3);
    assert.equal(await page.getByRole('link', { name: '猎手项目追踪', exact: true }).count(), 1);
    assert.equal(await page.getByRole('button', { name: /监控管理$|演示新推文|暂停更新/ }).count(), 0);
    assert.equal(await page.getByRole('heading', { name: /推文事件中心|中文译文|AI 摘要/ }).count(), 0);
    await text(page.getByRole('heading', { name: /最新推文动态/ }), '每页 6 条');
  });
  await check('remark leads every post; account grade, publication, body and media retained', async () => {
    const first = cards().first();
    assert.ok((await first.innerText()).startsWith('备 注\n重点关注主网上线'));
    await text(first, '@HyperliquidX'); await text(first, 'Introducing HyperEVM');
    assert.equal(await first.locator('.ik-score').innerText(), 'S'); assert.equal(await first.getByRole('img', { name: '演示配图：HyperEVM' }).count(), 1);
    const order = await first.evaluate(element => [...element.children].slice(0, 4).map(child => child.getBoundingClientRect().left));
    assert.ok(order.every((left, index) => index === 0 || left > order[index - 1]));
    const times = await cards().evaluateAll(elements => elements.map(el => Date.parse(el.dataset.published)));
    assert.ok(times.every((time, index) => index === 0 || time <= times[index - 1]));
  });
  await check('two-page pagination has six records and correct boundaries', async () => {
    await page.getByRole('button', { name: '下一页', exact: true }).click(); assert.equal(await cards().count(), 6);
    assert.equal(await cards().first().getAttribute('data-post'), 'demo-post-7'); await text(page.getByText('显示 7–12 条，共 12 条'), '7–12');
    assert.equal(await page.getByRole('button', { name: '下一页', exact: true }).isDisabled(), true);
    await page.getByRole('button', { name: '上一页', exact: true }).click(); assert.equal(await cards().first().getAttribute('data-post'), 'demo-post-1');
    assert.equal(await page.getByRole('button', { name: '上一页', exact: true }).isDisabled(), true);
  });
  await check('S/A/B grade filters work and reset page to one', async () => {
    for (const [grade, expected] of [['S', 3], ['A', 3], ['B', 6]]) {
      await page.getByRole('group', { name: '评级筛选' }).getByRole('button', { name: `${grade} 级`, exact: true }).click();
      assert.equal(await cards().count(), expected); assert.ok((await cards().evaluateAll(elements => elements.map(el => el.dataset.grade))).every(value => value === grade));
    }
    await page.getByRole('button', { name: '重置筛选', exact: true }).click(); assert.equal(await cards().count(), 6);
  });
  await check('remark, X handle, project and body search; empty recovery', async () => {
    for (const [query, expected] of [['主网上线', 2], ['@HYPERLIQUIDX', 2], ['EigenLayer', 1], ['API rate limits', 1]]) {
      await page.getByRole('searchbox', { name: '搜索推文', exact: true }).fill(query); assert.equal(await cards().count(), expected);
    }
    await page.getByRole('searchbox', { name: '搜索推文', exact: true }).fill('no_such_project'); await page.getByRole('heading', { name: '暂无符合条件的推文' }).waitFor();
    await page.getByRole('button', { name: '清空筛选', exact: true }).click(); assert.equal(await cards().count(), 6);
  });
  await check('24-hour, seven-day and important filters compose correctly', async () => {
    await page.getByLabel('时间范围', { exact: true }).selectOption('24'); await text(page.getByText('显示 1–6 条，共 9 条'), '9 条');
    await page.getByLabel('时间范围', { exact: true }).selectOption('168'); await text(page.getByText('显示 1–6 条，共 12 条'), '12 条');
    await page.getByLabel('只看重要推文').check(); assert.equal(await cards().count(), 3);
    await page.getByRole('group', { name: '评级筛选' }).getByRole('button', { name: 'S 级', exact: true }).click(); assert.equal(await cards().count(), 2);
  });
  await check('refresh resets filters without fetching posts or adding UI features', async () => {
    await page.getByRole('button', { name: '刷新', exact: true }).click();
    assert.equal(await cards().count(), 6); assert.equal(await page.getByLabel('时间范围', { exact: true }).inputValue(), 'all'); assert.equal(await page.getByLabel('只看重要推文').isChecked(), false);
    await text(page.getByRole('status'), '不会请求真实推文 API');
  });
  await check('demo original-post action gives explicit unsupported feedback', async () => {
    await cards().first().getByRole('button', { name: '查看 Hyperliquid 原文（演示）', exact: true }).click();
    await text(page.getByRole('status'), '不存在真实 X 原文链接');
    assert.equal(await cards().locator('a').count(), 0);
  });
  await check('account total opens right-side manager using shared controls and table', async () => {
    await openManager(); const bounds = await manager().boundingBox(); assert.ok(Math.abs(bounds.x + bounds.width - 1440) < 2); assert.ok(bounds.width <= 750);
    assert.equal(await manager().locator('tbody tr').count(), 10);
    for (const label of ['备注', '项目', 'X 账号', '评分', '状态', '操作']) assert.equal(await manager().getByRole('columnheader', { name: label, exact: true }).count(), 1);
    assert.equal(await manager().locator('.ik-table').count(), 1);
    await page.screenshot({ path: fileURLToPath(new URL('final-manager.png', directory)) });
  });
  await check('manager search supports note, project and handle', async () => {
    for (const query of ['主网上线', 'Hyperliquid', 'hyperliquidx']) {
      await manager().getByRole('searchbox', { name: '搜索监控账号', exact: true }).fill(query); assert.equal(await manager().locator('tbody tr').count(), 1);
    }
    await manager().getByRole('searchbox', { name: '搜索监控账号', exact: true }).fill('');
  });
  await check('manager keyboard trap, Escape, focus return and add cancel', async () => {
    for (let index = 0; index < 16; index++) { await page.keyboard.press(index % 2 ? 'Shift+Tab' : 'Tab'); assert.equal(await page.evaluate(() => !!document.activeElement.closest('dialog[open]')), true); }
    await manager().getByRole('button', { name: '＋ 添加监控账号', exact: true }).click(); await form();
    await manager().getByRole('button', { name: '取消', exact: true }).click(); assert.equal(await manager().getByLabel(/^X 用户名/).count(), 0);
    await page.keyboard.press('Escape'); await manager().waitFor({ state: 'hidden' });
    await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === '监控账号总数 10');
  });
  await check('add validates syntax, required fields and normalized duplicates', async () => {
    await openManager(); await manager().getByRole('button', { name: '＋ 添加监控账号', exact: true }).click();
    await form('bad handle'); await manager().getByRole('button', { name: '确认添加（模拟）' }).click(); await text(manager().getByRole('alert'), 'X 用户名应为');
    await form('@HYPERLIQUIDX'); await manager().getByRole('button', { name: '确认添加（模拟）' }).click(); await text(manager().getByRole('alert'), '已在演示监控列表');
    await form('@demo_project', ' ', ' '); await manager().getByRole('button', { name: '确认添加（模拟）' }).click(); await text(manager().getByRole('alert'), '项目名称应为');
    assert.equal(await page.getByTestId('account-count').textContent(), '10');
  });
  await check('add confirmation works once and creates no fabricated tweet history', async () => {
    await form(); await manager().getByLabel(/^项目评分/).selectOption('S');
    await manager().getByRole('button', { name: '确认添加（模拟）' }).click({ clickCount: 2 });
    await text(manager(), '@demo_project'); assert.equal(await manager().locator('tbody tr').count(), 11); assert.equal(await page.getByTestId('account-count').textContent(), '11');
    await page.keyboard.press('Escape'); await text(page.getByText('显示 1–6 条，共 12 条'), '12 条');
  });
  await check('delete cancel, nested focus and Escape affect only confirmation', async () => {
    await demo(); await openManager(); await manager().getByRole('button', { name: '删除 Hyperliquid', exact: true }).click();
    assert.equal(await modal().getByRole('button', { name: '取消', exact: true }).evaluate(el => document.activeElement === el), true);
    for (let index = 0; index < 6; index++) { await page.keyboard.press('Tab'); assert.equal(await modal().evaluate(el => el.contains(document.activeElement)), true); }
    await page.keyboard.press('Escape'); await modal().waitFor({ state: 'hidden' }); assert.equal(await manager().isVisible(), true);
    assert.equal(await manager().locator('tbody tr').count(), 10); assert.equal(await page.getByTestId('account-count').textContent(), '10');
  });
  await check('delete confirmed hides the account and its posts; refresh restores only filters', async () => {
    await manager().getByRole('button', { name: '删除 Hyperliquid', exact: true }).click();
    await modal().getByRole('button', { name: '确认删除（演示）', exact: true }).click(); await modal().waitFor({ state: 'hidden' });
    assert.equal(await manager().locator('tbody tr').count(), 9);
    await manager().getByRole('button', { name: '关闭弹窗', exact: true }).click(); await manager().waitFor({ state: 'hidden' });
    assert.equal(await page.getByTestId('account-count').textContent(), '9'); await text(page.getByText('显示 1–6 条，共 10 条'), '10 条');
    assert.equal(await cards().filter({ hasText: '@HyperliquidX' }).count(), 0);
    await page.getByRole('button', { name: '刷新', exact: true }).click(); assert.equal(await page.getByTestId('account-count').textContent(), '9');
    await page.reload(); await cards().first().waitFor(); assert.equal(await page.getByTestId('account-count').textContent(), '10');
  });
  await check('HTML-looking names and remarks are text, no executable markup', async () => {
    await openManager(); await manager().getByRole('button', { name: '＋ 添加监控账号' }).click();
    await form('@xss_demo', '<img src=x onerror=alert(1)>', '<svg onload=alert(1)>');
    await manager().getByRole('button', { name: '确认添加（模拟）' }).click();
    assert.equal(await manager().locator('tbody img, tbody svg[onload]').count(), 0); await text(manager(), '<img src=x onerror=alert(1)>');
    await page.keyboard.press('Escape');
  });
  await check('approved desktop/mobile layouts; drawer and table stay inside viewport', async () => {
    await demo();
    for (const width of [1440, 1920, 2560, 1020, 768, 390, 360]) {
      await page.setViewportSize({ width, height: width < 680 ? 844 : 1080 });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `document overflow ${width}`);
      assert.equal(await cards().count(), 6);
      if (width >= 1440 || width === 390) { await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: fileURLToPath(new URL(`final-${width}.png`, directory)), fullPage: true }); }
      if (width < 680) {
        const bounds = await cards().first().evaluate(el => [...el.children].slice(0, 3).map(child => child.getBoundingClientRect().top));
        assert.ok(bounds[0] <= bounds[1] && bounds[1] <= bounds[2]);
        await openManager(); assert.ok((await manager().boundingBox()).width <= width);
        assert.ok(await manager().getByRole('region', { name: '监控账号列表，可横向滚动', exact: true }).evaluate(el => el.scrollWidth > el.clientWidth));
        await page.screenshot({ path: fileURLToPath(new URL(`final-manager-${width}.png`, directory)) }); await page.keyboard.press('Escape');
      }
    }
  });
  await check('all demo activity remains local, no API/WSS/external calls or sessions', async () => {
    assert.deepEqual(errors, []); assert.deepEqual(violations, []); assert.deepEqual(await context.cookies(), []);
    assert.equal(await page.locator('input[type=password]').count(), 0);
  });
} catch (error) { console.error(error.stack); process.exitCode = 1; await page.screenshot({ path: fileURLToPath(new URL('failure.png', directory)) }).catch(() => {}); }
finally {
  await writeFile(new URL('browser-results.json', directory), JSON.stringify({ approvedPrototype: 'ikun-hunter-project-tracking-ui-prototype (2).html', checkedAt: new Date().toISOString(), base, results, runtimeErrors: errors, forbiddenRequests: violations }, null, 2) + '\n');
  if (!process.exitCode) await rm(new URL('failure.png', directory), { force: true });
  await browser.close();
}
