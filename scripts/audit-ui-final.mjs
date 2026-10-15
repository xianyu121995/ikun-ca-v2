import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const option = name => { const i = process.argv.indexOf(name); return i < 0 ? undefined : process.argv[i + 1]; };
const uiRoot = resolve(option('--ui-root') ?? resolve(root, '../ikun-ca-v2-worktrees/website'));
const origin = option('--origin') ?? 'http://127.0.0.1:3255';
assert.equal(new URL(origin).hostname, '127.0.0.1');
const output = resolve(root, 'var/b0/ui');
await mkdir(output, { recursive: true });
const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 }).trim();
const hash = value => createHash('sha256').update(value).digest('hex');
const pins = {
  website: '486294ac3255b08fdb13a307ee15f96c571020d9',
  'homepage-ui': 'eb93ac7739e0ce9d74fa9859f838a7bca294ce3e',
  'hunter-ui': '08065d700239b20fb4c887bbd0c85321904687f8',
  'tracking-ui': 'd90598f4bc595458ce26c5ee1c2e1618e318abc0',
};
const rules = JSON.parse(await readFile(resolve(root, 'docs/phase2/ownership.json'), 'utf8'));
const sources = [];
for (const [owner, commit] of Object.entries(pins)) {
  const cwd = resolve(uiRoot, '..', owner);
  assert.equal(execFileSync('git', ['rev-parse', 'HEAD'], { cwd, encoding: 'utf8' }).trim(), commit);
  assert.equal(execFileSync('git', ['status', '--porcelain'], { cwd, encoding: 'utf8' }).trim(), '');
  const rule = rules.rules.find(rule => rule.owner === owner);
  const files = git('diff', '--name-only', 'foundation-v0.1.0', commit).split('\n').filter(Boolean);
  assert.ok(files.every(path => rule.files.includes(path) || rule.prefixes.some(prefix => path.startsWith(prefix))), `Ownership drift: ${owner}`);
  sources.push({ owner, commit, clean: true, file_count: files.length });
}
// esbuild emits cwd-relative source names; reproduce the approved package command.
const originalCwd = process.cwd();
process.chdir(resolve(uiRoot, 'packages/ui'));
const { buildReview } = await import(pathToFileURL(resolve(uiRoot, 'packages/ui/scripts/review-build.mjs')));
const built = await buildReview();
process.chdir(originalCwd);
assert.deepEqual(Object.values(built.manifest.pages).map(page => page.commit), [pins['homepage-ui'], pins['hunter-ui'], pins['tracking-ui']]);
assert.equal(built.warnings.length, 0);
for (const [key, expected] of Object.entries(built.inputHashes)) {
  const slash = key.indexOf('/'); const page = built.manifest.pages[key.slice(0, slash)];
  const bytes = execFileSync('git', ['show', `${page.commit}:${key.slice(slash + 1)}`], { cwd: root });
  assert.equal(hash(bytes), expected);
}
const http = [];
for (const [path, method, status] of [['/', 'GET', 200], ['/hunter', 'GET', 200], ['/tracking', 'GET', 200], ['/api/v1/projects', 'GET', 404], ['/api/v1/projects', 'POST', 405]]) {
  const response = await fetch(origin + path, { method, signal: AbortSignal.timeout(5000) });
  assert.equal(response.status, status);
  if (status === 200) assert.match(response.headers.get('content-security-policy'), /connect-src 'none'/);
  await response.arrayBuffer(); http.push({ path, method, status });
}
for (const [asset, bytes] of [['/review.js', built.js], ['/review.css', built.css]]) {
  const response = await fetch(origin + asset, { signal: AbortSignal.timeout(5000) });
  assert.equal(response.status, 200);
  assert.equal(hash(Buffer.from(await response.arrayBuffer())), hash(bytes), `Running preview differs from final sources: ${asset}`);
}
const modulePath = option('--playwright');
assert.ok(modulePath, '--playwright must identify an installed test-only Playwright module');
const { chromium } = await import(pathToFileURL(resolve(modulePath)));
const browser = await chromium.launch({ headless: true, ...(option('--browser') ? { executablePath: option('--browser') } : {}) });
const layouts = [], styles = [], errors = [], forbiddenRequests = [], checks = [];
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (!request.url().startsWith(origin + '/') || request.method() !== 'GET' || /\/api\/|\/internal\//.test(request.url())) forbiddenRequests.push({ url: request.url(), method: request.method() });
  });
  for (const width of [1440, 1920, 2560, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of ['/', '/hunter', '/tracking']) {
      await page.goto(origin + route);
      await page.locator('.review-page h1').first().waitFor();
      await page.locator('.review-page .ik-search input').first().waitFor();
      const layout = await page.evaluate(() => ({
        sidebar: document.querySelectorAll('aside.ik-sidebar').length,
        main: document.querySelectorAll('main').length,
        links: [...document.querySelectorAll('.ik-nav a')].map(a => a.getAttribute('href')),
        active: document.querySelectorAll('.ik-nav [aria-current="page"]').length,
        client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth,
      }));
      assert.equal(layout.sidebar, 1); assert.equal(layout.main, 1); assert.equal(layout.active, 1);
      assert.deepEqual(layout.links, ['/', '/hunter', '/tracking']); assert.ok(layout.scroll <= layout.client + 1);
      layouts.push({ width, route, ...layout });
      if (width === 1920) {
        const style = await page.evaluate(() => {
          const get = selector => { const s = getComputedStyle(document.querySelector(selector)); return { font: s.fontFamily, size: s.fontSize, color: s.color, background: s.backgroundColor }; };
          return { title: get('.review-page h1'), search: get('.review-page .ik-search input'), scoreA: get('.review-page .ik-score--a'), scoreB: get('.review-page .ik-score--b') };
        });
        styles.push({ route, ...style });
        await page.screenshot({ path: resolve(output, `${route === '/' ? 'home' : route.slice(1)}-1920.png`), fullPage: false });
        const search = page.locator('.review-page .ik-search input').first();
        await search.fill('nonexistent_ui_acceptance_948310');
        await page.getByText(/没有符合条件的项目|暂无符合条件的推文/).first().waitFor();
        await search.fill('');
        checks.push(`${route}: empty search and restore`);
      }
    }
  }
  for (const { route, ...style } of styles.slice(1)) assert.deepEqual(style, (({ route, ...value }) => value)(styles[0]), `Computed style drift: ${route}`);
  await page.goto(origin + '/');
  await page.locator('.ik-nav a[href="/hunter"]').click();
  await page.waitForURL(origin + '/hunter');
  await page.locator('.ik-nav a[href="/tracking"]').click();
  await page.waitForURL(origin + '/tracking');
  await page.goBack(); assert.equal(new URL(page.url()).pathname, '/hunter');
  await page.goForward(); assert.equal(new URL(page.url()).pathname, '/tracking');
  checks.push('single navigation: three routes, back/forward, direct refresh');
  assert.deepEqual(errors, []); assert.deepEqual(forbiddenRequests, []);
} finally { await browser.close(); }
await writeFile(resolve(output, 'acceptance.json'), JSON.stringify({ checked_at: new Date().toISOString(), sources, input_hashes: built.inputHashes, asset_hashes: { js: hash(built.js), css: hash(built.css) }, http, layouts, styles, checks, errors, forbidden_requests: forbiddenRequests, ui_acceptance: 'PASS', business_acceptance: false, merge_authorized: false, production_authorized: false }, null, 2) + '\n');
console.log(`UI acceptance PASS: 4 clean final commits, ${Object.keys(built.inputHashes).length} pinned inputs, 12 responsive route checks, computed styles identical, no API/external requests`);
