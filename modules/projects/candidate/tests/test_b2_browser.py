"""Real pinned Next build + B1 + B0-owned private UDS + temporary Projects DB."""
import json
import os
import socket
import signal
import secrets
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

from projects_service.migration import FormalDatabase
from projects_service.service import Service
from test_b2_domain import call, uid, FIELDS, event
from test_b2_home import home_create

ROOT=Path(__file__).resolve().parents[4]
INTEGRATION=ROOT/'modules/projects/integration'
NODE=Path('/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node')
def build_sha():return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
class WebsiteFixture(dict):
    def __repr__(self):return f"WebsiteFixture(origin={self['origin']!r}, accounts=<synthetic-redacted>)"

@pytest.fixture
def website(tmp_path_factory):
    tmp=tmp_path_factory.mktemp('b2-real-website');db=FormalDatabase(tmp/'data/projects/projects.db');db.migrate();domain=Service(db)
    for i in range(113):home_create(domain,name=f'验收项目{i:03}',rating=['S','A','B'][i%3],milestone={'date':'2099-12-31','hour':['00','23',None][i%3],'title':'独立重要事件','status':'estimated'})
    for i in range(12):home_create(domain,name=f'已完成{i:02}',complete=True,progress_stage='completed')
    for i in range(12):home_create(domain,name=f'其他项目{i:02}',rating=None)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}';credentials=tmp/'synthetic-accounts.json'
    subprocess.run([str(NODE),str(INTEGRATION/'tests/provision-fixture.mjs'),str(tmp/'data'),origin,str(credentials)],check=True,capture_output=True)
    env={**os.environ,'DATA_ROOT':str(tmp/'data'),'PROJECTS_PYTHON':str(ROOT/'modules/projects/candidate/.venv/bin/python'),'IKUN_AUTH_ORIGIN':origin,'IKUN_AUTH_DEV':'1','PORT':str(port),'B2_BUILD_SHA':build_sha()}
    env['PROJECTS_INGEST_HUNTER_TOKEN']=secrets.token_hex(32);env['PROJECTS_INGEST_TRACKING_TOKEN']=secrets.token_hex(32)
    log=(tmp/'website.log').open('w');process=subprocess.Popen([str(NODE),str(INTEGRATION/'start-website.mjs')],env=env,stdout=log,stderr=log)
    try:
        for _ in range(200):
            try:
                if httpx.get(origin+'/health/ready').status_code==200:break
            except httpx.HTTPError:pass
            if process.poll() is not None:raise AssertionError((tmp/'website.log').read_text())
            time.sleep(.1)
        else:raise AssertionError((tmp/'website.log').read_text())
        yield WebsiteFixture(origin=origin,accounts=json.loads(credentials.read_text()),tmp=tmp,domain=domain,env=env,process=process)
    finally:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()

def login(client,website,role):
    response=client.post('/api/v1/auth/login',json=website['accounts'][role],headers={'Origin':website['origin']});assert response.status_code==200
    return response.json()['data']['csrf_token']

def test_real_http_permissions_and_projection(website):
    with httpx.Client(base_url=website['origin']) as client:
        assert client.get('/api/v1/projects').status_code==401
        csrf=login(client,website,'user')
        assert client.get('/api/v1/projects/home-summary').json()['data']['tracked_total']==113
        page=client.get('/api/v1/projects?view=home-v1&collection=tracked&limit=9').json()['data'];assert page['total']==113 and len(page['items'])==9
        assert client.post('/api/v1/projects',json=FIELDS,headers={'Origin':website['origin'],'X-CSRF-Token':csrf,'Idempotency-Key':uid(),'X-Role':'superadmin'}).status_code==403
        assert client.get('/api/v1/projects?view=home-v1&collection=other&collection=tracked').status_code==422
        assert client.get('/api/v1/projects?collection=other').status_code==422
        assert client.get('/api/v1/projects?tenant_id=foreign').status_code==403
        assert client.get('/api/v1/projects?view=unknown').status_code==422
        assert client.get('/api/v1/auth/me').json()['data']['capabilities']['can_manage_users'] is False
        assert client.post('/internal/v1/ingest/hunter',json={}).status_code==401
        data=event();headers={'Authorization':'Bearer '+website['env']['PROJECTS_INGEST_HUNTER_TOKEN']}
        first=client.post('/internal/v1/ingest/hunter',json=data,headers=headers);assert first.status_code==200
        repeated=client.post('/internal/v1/ingest/hunter',json=data,headers=headers).json()['data'];assert repeated['duplicate'] and repeated['project_id']==first.json()['data']['project_id']
        receipt=client.get('/internal/v1/receipts/hunter/'+data['event_id'],headers=headers);assert receipt.status_code==200 and receipt.json()['data']['receipt_id']==repeated['receipt_id']
        assert client.post('/internal/v1/ingest/tracking',json=data,headers=headers).status_code==401

def test_actual_entries_without_proxy(tmp_path):
    data_root=tmp_path/'data';FormalDatabase(data_root/'projects/projects.db').migrate()
    output=tmp_path/'accounts.json';origin='http://127.0.0.1:31997'
    subprocess.run([str(NODE),str(INTEGRATION/'tests/provision-fixture.mjs'),str(data_root),origin,str(output)],check=True,capture_output=True)
    env={**os.environ,'DATA_ROOT':str(data_root),'IKUN_AUTH_ORIGIN':origin,'IKUN_AUTH_DEV':'1','TEST_ACCOUNTS':str(output),'PROJECTS_PYTHON':str(ROOT/'modules/projects/candidate/.venv/bin/python'),'NODE_ENV':'production','B2_BUILD_SHA':build_sha()}
    result=subprocess.run([str(NODE),'--import',str(ROOT/'modules/projects/.preview/node_modules/tsx/dist/loader.mjs'),'--test',str(INTEGRATION/'tests/guards.test.mjs')],env=env,capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr

@pytest.mark.parametrize('width',[1440,390])
def test_real_homepage_server_pages_editor_and_visual(website,width):
    with sync_playwright() as p:
        candidates=sorted(Path.home().glob('Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'))
        browser=p.chromium.launch(executable_path=str(candidates[-1]),headless=True)
        page=browser.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(website['origin']+'/login')
        assert page.locator('input[name=username]').count(),page.locator('body').inner_text()
        page.locator('input[name=username]').fill(website['accounts']['admin']['username']);page.locator('input[name=password]').fill(website['accounts']['admin']['password']);page.get_by_role('button',name='登录',exact=True).click()
        expect(page.get_by_role('heading',name='持续跟踪项目',exact=True)).to_be_visible();expect(page.locator('.hpv2-table-footer')).to_contain_text('共 113 条')
        page.get_by_label('表格排序',exact=True).select_option('discovered:asc')
        page.get_by_label('全选当前页',exact=True).check();expect(page.get_by_role('button',name='移除已选 (9)',exact=True)).to_be_enabled()
        page.get_by_label('下一页',exact=True).click();expect(page.locator('.hpv2-table-footer')).to_contain_text('显示 10–18 条');expect(page.get_by_label('全选当前页',exact=True)).not_to_be_checked()
        page.get_by_label('搜索项目',exact=True).fill('验收项目112');expect(page.locator('.hpv2-table-footer')).to_contain_text('共 1 条')
        expect(page.locator('.hpv2-events tbody tr')).to_have_count(3)
        page.get_by_role('button',name='已完成记录 (12)',exact=True).click();expect(page.get_by_role('dialog')).to_be_visible();page.get_by_label('下一页记录',exact=True).click();expect(page.get_by_role('dialog')).to_contain_text('2 / 2 · 12');page.keyboard.press('Escape')
        page.get_by_role('button',name='其他项目 (12)',exact=True).click();page.get_by_label('下一页记录',exact=True).click();expect(page.get_by_role('dialog')).to_contain_text('2 / 2 · 12');page.keyboard.press('Escape')
        page.get_by_role('button',name='＋ 新增项目',exact=True).click();page.get_by_label('项目名称',exact=True).fill(f'浏览器新增{width}');page.get_by_label('项目简介',exact=True).fill('真实数据库保存');page.get_by_label('近期重要时间',exact=True).fill('2099-12-30');page.get_by_label('重要时间：小时',exact=True).select_option('23');page.get_by_label('重要事件',exact=True).fill('浏览器事件');page.get_by_role('button',name='保存资料',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
        page.get_by_label('搜索项目',exact=True).fill(f'浏览器新增{width}');expect(page.locator('.hpv2-projects button[data-project-id]').filter(has_text=f'浏览器新增{width}')).to_be_visible()
        page.reload();page.get_by_label('搜索项目',exact=True).fill(f'浏览器新增{width}');expect(page.locator('.hpv2-projects button[data-project-id]').filter(has_text=f'浏览器新增{width}')).to_be_visible()
        page.screenshot(path=str(website['tmp']/f'homepage-{width}.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        row=page.locator('.hpv2-projects tbody tr').filter(has_text=f'浏览器新增{width}')
        project_id=row.locator('button[data-project-id]').get_attribute('data-project-id')
        delete_results=[]
        page.on('response',lambda response:delete_results.append((response.status,response.json())) if response.request.method=='DELETE' else None)
        row.get_by_role('button',name='编辑',exact=True).click();page.get_by_label('备注',exact=True).fill('浏览器编辑持久化');page.get_by_role('button',name='保存资料',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
        row.get_by_role('button',name='移除',exact=True).click();page.get_by_role('button',name='标记完成并移除',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
        page.get_by_role('button',name='已完成记录 (13)',exact=True).click()
        # The newly completed record may be on any stable cursor page; find it using real pages.
        while not page.locator('.hpv2-record-row').filter(has_text=f'浏览器新增{width}').count():
            previous=page.locator('.hpv2-record-row strong').first.inner_text()
            page.get_by_label('下一页记录',exact=True).click()
            expect(page.locator('.hpv2-record-row strong').first).not_to_have_text(previous)
        page.locator('.hpv2-record-row').filter(has_text=f'浏览器新增{width}').get_by_role('button',name='恢复跟踪',exact=True).click()
        expect(page.get_by_role('dialog')).to_have_attribute('aria-busy','false')
        page.get_by_role('dialog').get_by_role('button',name='关闭弹窗',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0);expect(page.locator('.hpv2-projects button[data-project-id]').filter(has_text=f'浏览器新增{width}')).to_be_visible()
        page.locator('.hpv2-projects button[data-project-id]').filter(has_text=f'浏览器新增{width}').click();page.get_by_role('button',name='删除主页条目',exact=True).click();page.get_by_role('button',name='确认移除主页',exact=True).click()
        try:expect(page.get_by_role('dialog')).to_have_count(0)
        except AssertionError:raise AssertionError(str(delete_results))
        stored=call(website['domain'],'get',target=project_id)[1]
        assert stored['home_membership']=='removed' and stored['progress_stage']=='researching' and stored['notes']=='浏览器编辑持久化'
        assert not errors
        browser.close()

@pytest.mark.parametrize('failure',['TERM','KILL','IPC_KILL'])
def test_actual_website_managed_process_tree_and_readiness(website,failure):
    root=website['process'];rows=[]
    for line in subprocess.check_output(['ps','-axo','pid=,ppid=,command='],text=True).splitlines():
        parts=line.strip().split(None,2)
        if len(parts)==3:rows.append((int(parts[0]),int(parts[1]),parts[2]))
    owned={root.pid}
    while True:
        expanded=owned|{pid for pid,parent,_ in rows if parent in owned}
        if expanded==owned:break
        owned=expanded
    children=[(pid,cmd) for pid,parent,cmd in rows if pid in owned and pid!=root.pid]
    python=[pid for pid,cmd in children if '/ipc-entry.py' in cmd and 'process-entry.js' not in cmd]
    assert len(python)==1 and len(children)>=4
    files=subprocess.check_output(['lsof','-a','-p',str(python[0]),'-U','-Fn'],text=True)
    paths=[Path(line[1:].split(' type=')[0]) for line in files.splitlines() if line.startswith('n/private/tmp/ikp-') and '/p.sock' in line]
    assert paths
    socket_path=paths[0]
    if failure=='IPC_KILL':
        os.kill(python[0],signal.SIGKILL)
        with httpx.Client(base_url=website['origin']) as client:
            login(client,website,'admin')
            for _ in range(50):
                if client.get('/health/ready').status_code==503:break
                time.sleep(.05)
            assert client.get('/health/ready').status_code==503
            assert client.get('/api/v1/projects').status_code==503
        return
    if failure=='TERM':root.terminate()
    else:root.kill()
    root.wait(timeout=15)
    def running(pid):
        value=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True)
        return bool(value.stdout.strip()) and not value.stdout.strip().startswith('Z')
    for _ in range(150):
        if not any(running(pid) for pid,_ in children):break
        time.sleep(.1)
    assert not any(running(pid) for pid,_ in children)
    assert not socket_path.exists()
    if socket_path.parent.exists():socket_path.parent.rmdir()
    with pytest.raises(httpx.HTTPError):httpx.get(website['origin']+'/health/live',timeout=1)

def test_browser_unknown_uses_original_receipt_and_never_reposts(website):
    with sync_playwright() as p:
        candidates=sorted(Path.home().glob('Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'))
        browser=p.chromium.launch(executable_path=str(candidates[-1]),headless=True);page=browser.new_page()
        page.goto(website['origin']+'/login');page.locator('input[name=username]').fill(website['accounts']['admin']['username']);page.locator('input[name=password]').fill(website['accounts']['admin']['password']);page.get_by_role('button',name='登录',exact=True).click();expect(page.locator('.hpv2-table-footer')).to_contain_text('共 113 条')
        posts=[]
        def lose_ack(route):
            if route.request.method=='POST':
                posts.append(route.request.headers['idempotency-key']);response=route.fetch();assert response.status==201;route.abort('timedout')
            else:route.continue_()
        page.route('**/api/v1/projects?view=home-v1',lose_ack)
        page.route('**/api/v1/projects/operations/*',lambda route:route.fulfill(status=404,content_type='application/json',body=json.dumps({'error':{'code':'NOT_FOUND','message':'尚未找到','retryable':False},'request_id':uid()})))
        page.get_by_role('button',name='＋ 新增项目',exact=True).click();page.get_by_label('项目名称',exact=True).fill('回执丢失测试');page.get_by_role('button',name='保存资料',exact=True).click()
        expect(page.get_by_role('dialog')).to_contain_text('结果待核实');page.get_by_role('button',name='核对结果',exact=True).click();expect(page.get_by_role('dialog')).to_contain_text('结果仍待核对');assert len(posts)==1
        page.unroute('**/api/v1/projects/operations/*');page.get_by_role('button',name='核对结果',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
        assert len(posts)==1
        result=call(website['domain'],'list',query={'q':'回执丢失测试'})[1];assert len(result['items'])==1
        browser.close()

def test_browser_ignores_superseded_query_response(website):
    with sync_playwright() as p:
        candidates=sorted(Path.home().glob('Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'))
        browser=p.chromium.launch(executable_path=str(candidates[-1]),headless=True);page=browser.new_page()
        page.goto(website['origin']+'/login');page.locator('input[name=username]').fill(website['accounts']['forced']['username']);page.locator('input[name=password]').fill(website['accounts']['forced']['password']);page.get_by_role('button',name='登录',exact=True).click()
        expect(page.get_by_role('heading',name='首次登录：修改初始密码',exact=True)).to_be_visible()
        page.locator('input[name=current_password]').fill(website['accounts']['forced']['password']);page.locator('input[name=new_password]').fill('Browser-Changed-Password-873!');page.locator('input[name=confirm_password]').fill('Browser-Changed-Password-873!');page.get_by_role('button',name='保存新密码',exact=True).click();expect(page.locator('.hpv2-table-footer')).to_contain_text('共 113 条')
        expect(page.get_by_role('button',name='＋ 新增项目',exact=True)).to_be_disabled()
        held=[]
        def reorder(route):
            if 'q=验收项目000' in route.request.url or 'q=%E9%AA%8C%E6%94%B6%E9%A1%B9%E7%9B%AE000' in route.request.url:held.append(route)
            else:route.continue_()
        page.route('**/api/v1/projects?*',reorder)
        with page.expect_request(lambda r:'项目000' in r.url or '%E9%AA%8C%E6%94%B6%E9%A1%B9%E7%9B%AE000' in r.url):page.get_by_label('搜索项目',exact=True).fill('验收项目000')
        page.get_by_label('搜索项目',exact=True).fill('验收项目112');expect(page.locator('.hpv2-projects button[data-project-id]')).to_have_text(['验验收项目112'])
        assert held
        for route in held:route.continue_()
        expect(page.locator('.hpv2-table-footer')).to_contain_text('共 1 条');expect(page.locator('.hpv2-projects button[data-project-id]')).to_have_text(['验验收项目112'])
        browser.close()
