import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtemp, mkdir, realpath, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { createServer } from 'node:net';
import { existsSync } from 'node:fs';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/lvlei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = fileURLToPath(new URL('..', import.meta.url));
const scratch = await realpath(await mkdtemp(resolve(tmpdir(), 'ikun-tracking-browser-')));
const port = await new Promise(done => { const server=createServer();server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>done(port));}); });
const config = resolve(scratch,'config.json');
await writeFile(config, JSON.stringify({db_path:resolve(scratch,'tracking.db'),port}));
const admin='browser-fixture-admin-credential-xxxxxxxx';
const reader='browser-fixture-reader-credential-xxxxxxx';
const child=spawn(resolve(root,'.venv/bin/python'),['-m','tracking.cli','api','--config',config],{
  cwd:root, env:{...process.env,IKUN_TRACKING_ADMIN_TOKEN:admin,IKUN_TRACKING_READ_TOKEN:reader},stdio:'ignore'
});
let browser;
try {
  const base=`http://127.0.0.1:${port}`;
  for(let i=0;i<100;i++){try{if((await fetch(base+'/healthz')).ok)break;}catch{}await new Promise(r=>setTimeout(r,50));}
  const executable=process.env.CHROMIUM_EXECUTABLE || (existsSync(chromium.executablePath()) ? chromium.executablePath() : '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
  browser=await chromium.launch({headless:true,executablePath:executable});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage(), errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base+'/tracking');
  await page.locator('#access-key').fill(admin);
  await page.locator('#login-form button').click();
  await page.locator('#add').waitFor({state:'visible'});
  await page.locator('#add').click();
  await page.locator('#project-name').fill('测试项目 <img src=x onerror=alert(1)>');
  await page.locator('#project-id').fill('prj_550e8400-e29b-41d4-a716-446655440000');
  await page.locator('#project-handle').fill('@demo_project');
  await page.locator('#confirmed').check();
  await page.locator('#save-project').click();
  await page.getByRole('button',{name:'编辑',exact:true}).waitFor();
  assert.equal(await page.locator('#projects img').count(),0);
  await page.getByRole('button',{name:'编辑',exact:true}).click();
  await page.locator('#project-name').fill('示例项目 · 隔离测试');
  await page.locator('#project-notes').fill('人工确认后的项目监控');
  await page.locator('#save-project').click();
  await page.getByText('示例项目 · 隔离测试',{exact:true}).waitFor();
  await page.getByRole('button',{name:'停止',exact:true}).click();
  await page.getByRole('button',{name:'恢复',exact:true}).waitFor();
  await page.getByRole('button',{name:'恢复',exact:true}).click();
  await page.getByRole('button',{name:'停止',exact:true}).waitFor();
  await page.locator('#search').fill('没有此项目');
  await page.locator('#empty').waitFor({state:'visible'});
  await page.locator('#search').fill('');
  await mkdir(resolve(root,'artifacts'),{recursive:true});
  await page.screenshot({path:resolve(root,'artifacts/tracking-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
  await page.screenshot({path:resolve(root,'artifacts/tracking-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('button',{name:'移除',exact:true}).click();
  await page.getByText('移除请求处理中',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  await page.locator('#logout').click();
  await page.locator('#access-key').fill(reader);
  await page.locator('#login-form button').click();
  await page.locator('#workspace').waitFor({state:'visible'});
  assert.equal(await page.locator('#add').isVisible(),false);
  assert.equal(await page.getByRole('button',{name:'编辑',exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:'移除',exact:true}).count(),0);
  assert.deepEqual(errors,[]);
  process.stdout.write('Browser smoke passed: login, create, edit, stop, resume, pending removal, search, reader permissions, XSS, 1440/390px layout.\n');
} finally {
  if(browser)await browser.close();
  child.kill('SIGTERM');
  await new Promise(done=>child.once('exit',done));
}
