#!/usr/bin/env python3
"""Actual received Next production entry P0. Run the complete lifecycle under heavy-lock."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from c0_test_fixture import ROOT, NODE, PYTHON, cli, environment, migrate_projects, provision
from readonly_entry_matrix import empty_store, populated

FIELDS = dict(name='C0 actual HTTP', rating='A', description='C0 synthetic validation', website_url=None,
              notes='', category=None, progress_stage='researching', progress_percent=37.0,
              token_date=None, token_date_status='unconfirmed')
OUTPUT = ROOT / 'release-integration/c0-lite/evidence'
CHECKS = []
PRIVATE_PASSWORDS = []


def check(condition, label, **detail):
    CHECKS.append({'check': label, 'result': 'PASS' if condition else 'FAIL', **detail})
    if not condition:
        raise AssertionError(label)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def db_fingerprint(path, tables=None):
    with sqlite3.connect(Path(path).as_uri()+'?mode=ro', uri=True) as con:
        con.execute('PRAGMA query_only=ON')
        if tables is None:
            values=list(con.iterdump())
        else:
            values={table:con.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall() for table in tables}
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def seed_projects(data_root):
    from projects_service.migration import FormalDatabase
    from projects_service.service import Service
    from projects_service.transport import Rpc
    service=Service(FormalDatabase(data_root/'projects/projects.db'))
    actor={'user_id':'synthetic_fixture','tenant_id':'ikun-main','role':'superadmin'}
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    for index in range(137):
        completed=113<=index<125
        fields={**FIELDS,'name':f'C0验收项目{index:03}','rating':None if index>=125 else ['S','A','B'][index%3],
                'progress_stage':'completed' if completed else 'researching'}
        milestone={'date':(today+timedelta(days=1)).isoformat(),'hour':['00','23',None][index%3],
                   'title':'独立重要事件','status':'estimated'}
        result=service.execute(Rpc(operation='create',principal=actor,request_id=str(uuid.uuid4()),
                                  idempotency_key=str(uuid.uuid4()),contract='projects-home-v1',
                                  body={'fields':fields,'milestone':milestone,'complete':completed}))
        if result[0]!=201:
            raise AssertionError('SYNTHETIC_PROJECT_SEED_FAILED')
        if index>=125:
            project=result[1]['project']
            service.execute(Rpc(operation='membership',principal=actor,request_id=str(uuid.uuid4()),
                                idempotency_key=str(uuid.uuid4()),contract='projects-home-v1',target=project['project_id'],
                                if_match=f'"rev-{project["revision"]}"',body={'action':'remove'}))


def activate(client, origin, account):
    response=client.post('/api/v1/auth/login',json=account,headers={'Origin':origin})
    check(response.status_code==200,'real_login',role=account['username'])
    value=response.json()['data']
    if value['must_change_password']:
        changed=secrets.token_urlsafe(24)
        PRIVATE_PASSWORDS.extend([account['password'],changed])
        response=client.post('/api/v1/auth/password',json={'current_password':account['password'],'new_password':changed},
                             headers={'Origin':origin,'X-CSRF-Token':value['csrf_token']})
        check(response.status_code==200,'real_first_password_change',role=account['username'])
        account['password']=changed
    return client.get('/api/v1/auth/me').json()['data']['csrf_token']


def write_headers(origin, csrf, revision=None, key=None):
    value={'Origin':origin,'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':key or str(uuid.uuid4())}
    if revision is not None:
        value['If-Match']=f'"rev-{revision}"'
    return value


def sse_waiter(client, origin):
    started=threading.Event();finished=threading.Event();state={}
    cookies=httpx.Cookies(client.cookies)
    def run():
        try:
            with httpx.Client(base_url=origin,cookies=cookies,trust_env=False,timeout=12) as reader:
                with reader.stream('GET','/api/v1/events/stream',headers={'Last-Event-ID':'9999999999999'}) as response:
                    state['status']=response.status_code
                    for line in response.iter_lines():
                        started.set()
        except httpx.HTTPError:
            state['transport_closed']=True
        finally:
            started.set();finished.set()
    thread=threading.Thread(target=run,daemon=True);thread.start()
    check(started.wait(8) and state.get('status')==200,'actual_quiet_sse_open')
    return finished,thread


def http_p0(origin, data_root, accounts):
    with httpx.Client(base_url=origin,trust_env=False,timeout=12) as anon, \
         httpx.Client(base_url=origin,trust_env=False,timeout=12) as admin, \
         httpx.Client(base_url=origin,trust_env=False,timeout=12) as user:
        for page in ['/','/hunter','/tracking']:
            r=anon.get(page)
            check(r.status_code in (302,303,307,308) and '/login' in r.headers.get('location',''),'AUTH-01 anonymous page',path=page)
        for path in ['/api/v1/projects','/api/v1/tracking/subscriptions','/api/v1/auth/me']:
            check(anon.get(path).status_code==401,'AUTH-01 anonymous API',path=path)
        before=db_fingerprint(data_root/'projects/projects.db')
        admin_csrf=activate(admin,origin,accounts['admin'])
        user_csrf=activate(user,origin,accounts['user'])
        check(db_fingerprint(data_root/'projects/projects.db')==before,'ISO-01 Auth operations do not change Projects')
        for method in ['POST','PUT','PATCH','DELETE']:
            r=user.request(method,'/api/v1/projects',json=FIELDS,headers=write_headers(origin,user_csrf))
            check(r.status_code==403,'AUTH-02 user write denied',method=method)
        forged=anon.post('/api/v1/projects',json=FIELDS,headers={**write_headers(origin,'forged'),'X-Role':'superadmin','X-User-Id':'fake'})
        check(forged.status_code==401,'AUTH-02 forged identity rejected')
        check(admin.get('/api/v1/projects?tenant_id=foreign').status_code==403,'AUTH-02 foreign scope rejected')
        check(admin.post('/api/v1/projects',json=FIELDS,headers={'Origin':origin,'Idempotency-Key':str(uuid.uuid4())}).status_code==403,'AUTH-02 missing CSRF rejected')
        check(admin.post('/api/v1/projects',json=FIELDS,headers={**write_headers(origin,admin_csrf),'Origin':'https://evil.invalid'}).status_code==403,'AUTH-02 cross origin rejected')
        for path in ['/auth/users','/api/v1/auth/users']:
            check(admin.get(path).status_code==404,'AUTH-02 web account administration absent',path=path)
        check(user.get('/api/v1/tracking/subscriptions').status_code==501,'protected Tracking API explicitly not implemented')
        check(user.get('/api/v1/hunter/accounts').status_code==403,'Hunter account management remains admin only')

        key=str(uuid.uuid4());headers=write_headers(origin,admin_csrf,key=key)
        first=admin.post('/api/v1/projects',json=FIELDS,headers=headers)
        check(first.status_code==201,'PRO-01 actual create')
        project=first.json()['data'];target=project['project_id']
        repeat=admin.post('/api/v1/projects',json=FIELDS,headers=headers)
        check(repeat.status_code==201 and repeat.json()['data']['project_id']==target,'PRO-01 idempotent replay')
        changed=admin.patch('/api/v1/projects/'+target,json={'notes':'persisted from HTTP'},headers=write_headers(origin,admin_csrf,1))
        check(changed.status_code==200,'PRO-01 actual edit')
        project=changed.json()['data']
        conflict=admin.patch('/api/v1/projects/'+target,json={'notes':'stale'},headers=write_headers(origin,admin_csrf,1))
        check(conflict.status_code==409,'PRO-01 revision conflict')
        check(admin.get('/api/v1/projects/'+target).json()['data']['notes']=='persisted from HTTP','PRO-01 persisted reread')
        lost_key=str(uuid.uuid4())
        # Deliberately discard a successful write response without a second POST; query its original receipt.
        with admin.stream('POST','/api/v1/projects',json={**FIELDS,'name':'C0 discarded response'},headers=write_headers(origin,admin_csrf,key=lost_key)) as dropped:
            check(dropped.status_code==201,'PRO-01 original write accepted before response discarded')
        receipt=admin.get('/api/v1/projects/operations/'+lost_key,params={'method':'POST','path':'/api/v1/projects','contract':'phase2-v1.0.0'})
        check(receipt.status_code==200 and receipt.json()['data']['state']=='succeeded','PRO-01 original receipt recovery without retry')
        query={'view':'home-v1','collection':'tracked','limit':37,'sort':'name','direction':'asc'}
        seen=[];cursor=None;total=None
        while True:
            page=user.get('/api/v1/projects',params={**query,**({'cursor':cursor} if cursor else {})}).json()['data']
            total=page['total'];seen.extend(x['project']['project_id'] for x in page['items']);cursor=page['next_cursor']
            if not cursor:break
        check(total>100 and len(seen)==len(set(seen))==total,'PRO-01 database pagination beyond 100',total=total)
        filtered=user.get('/api/v1/projects',params={**query,'q':'C0验收项目112'}).json()['data']
        check(filtered['total']==1 and len(filtered['items'])==1,'PRO-01 server filtering before pagination')
        check(user.get('/api/v1/projects/milestones').json()['data']['items'],'PRO-02 independent important events')

        for name in ('hunter','tracking'):
            with sqlite3.connect(data_root/name/(name+'.db')) as con:
                con.execute('CREATE TABLE retained_reference(project_id TEXT PRIMARY KEY,value TEXT)')
                con.execute('INSERT INTO retained_reference VALUES(?,?)',(target,'unchanged synthetic reference'))
        sentinels={name:digest(data_root/name/(name+'.db')) for name in ('hunter','tracking')}
        accounts_before=db_fingerprint(data_root/'auth/auth.db',['auth_users'])
        completed=admin.post('/api/v1/projects/'+target+'/completion?view=home-v1',json={},headers=write_headers(origin,admin_csrf,project['revision']))
        check(completed.status_code==200,'PRO-02 actual completion')
        completed=completed.json()['data']
        check(completed['project']['progress_stage']=='completed' and completed['completion']['previous_percent']==37.0,'PRO-02 prior progress snapshot')
        restored=admin.post('/api/v1/projects/'+target+'/restore?view=home-v1',json={},headers=write_headers(origin,admin_csrf,completed['project']['revision']))
        check(restored.status_code==200,'PRO-02 actual restore')
        restored=restored.json()['data']['project']
        check(restored['progress_stage']=='researching' and restored['progress_percent']==37.0,'PRO-02 restores actual prior progress')
        removed=admin.delete('/api/v1/projects/'+target,headers=write_headers(origin,admin_csrf,restored['revision']))
        check(removed.status_code==200 and removed.json()['data']['home_membership']=='removed','PRO-02 membership removal is separate')
        check(removed.json()['data']['progress_stage']=='researching','PRO-02 membership removal does not complete')
        check(all(digest(data_root/name/(name+'.db'))==value for name,value in sentinels.items()),'ISO-01 synthetic other-store references unchanged')
        check(db_fingerprint(data_root/'auth/auth.db',['auth_users'])==accounts_before,'ISO-01 Projects does not change Auth users')
        with sqlite3.connect(data_root/'projects/projects.db') as con:
            names={x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        check(not {'auth_users','auth_sessions','principals','sessions'} & names,'ISO-01 no login store in Projects')

        done,thread=sse_waiter(user,origin)
        check(user.post('/api/v1/auth/logout',json={},headers=write_headers(origin,user_csrf)).status_code==200,'AUTH-03 actual logout')
        check(done.wait(6),'AUTH-03 logout revokes live SSE');thread.join(timeout=1)
        check(user.get('/api/v1/projects').status_code==401,'AUTH-03 logout revokes old API session')
        user_csrf=activate(user,origin,accounts['user'])
        done,thread=sse_waiter(user,origin)
        cli(data_root,origin,'disable',accounts['user']['username'])
        check(user.get('/api/v1/projects').status_code==401 and done.wait(6),'AUTH-03 real CLI disable revokes API and SSE');thread.join(timeout=1)
        cli(data_root,origin,'enable',accounts['user']['username'])
        user_csrf=activate(user,origin,accounts['user'])
        done,thread=sse_waiter(user,origin)
        reset=secrets.token_urlsafe(24);PRIVATE_PASSWORDS.extend([accounts['user']['password'],reset]);cli(data_root,origin,'reset-password',accounts['user']['username'],reset)
        accounts['user']['password']=reset
        check(user.get('/api/v1/projects').status_code==401 and done.wait(6),'AUTH-03 real CLI reset revokes API and SSE');thread.join(timeout=1)
        user_csrf=activate(user,origin,accounts['user'])
        done,thread=sse_waiter(admin,origin)
        recovered=secrets.token_urlsafe(24);PRIVATE_PASSWORDS.extend([accounts['admin']['password'],recovered]);cli(data_root,origin,'recover-admin',accounts['admin']['username'],recovered)
        accounts['admin']['password']=recovered
        check(admin.get('/api/v1/projects').status_code==401 and done.wait(6),'AUTH-03 real CLI recovery revokes API and SSE');thread.join(timeout=1)
        activate(admin,origin,accounts['admin'])
        with sqlite3.connect(data_root/'auth/auth.db') as con:
            count=con.execute("SELECT count(*) FROM auth_users WHERE role='superadmin' AND enabled=1").fetchone()[0]
        check(count==1,'AUTH-03 exactly one effective superadmin')


def browsers(origin, accounts, output):
    from playwright.sync_api import sync_playwright, expect
    candidates=sorted(Path.home().glob('Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'))
    if not candidates:
        raise RuntimeError('INSTALLED_CHROMIUM_REQUIRED')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(candidates[-1]),headless=True)
        try:
            forced_context=browser.new_context(viewport={'width':390,'height':844})
            forced=forced_context.new_page();forced.goto(origin+'/login')
            forced.locator('input[name=username]').fill(accounts['forced']['username'])
            forced.locator('input[name=password]').fill(accounts['forced']['password'])
            forced.get_by_role('button',name='登录',exact=True).click()
            expect(forced.get_by_role('heading',name='首次登录：修改初始密码',exact=True)).to_be_visible()
            check(len(accounts['forced']['password'])==10,'PASSWORD10 real CLI accepted ten-character initial password')
            for name in ('new_password','confirm_password'):
                field=forced.locator('input[name='+name+']')
                check(field.get_attribute('minlength')=='10' and field.get_attribute('maxlength')=='128','PASSWORD10 actual DOM bounds',field=name)
                field.fill('x'*9)
                check(field.evaluate('el => el.validity.tooShort'),'PASSWORD10 browser rejects nine characters',field=name)
            me=forced_context.request.get(origin+'/api/v1/auth/me').json()['data']
            rejected=forced_context.request.post(origin+'/api/v1/auth/password',data={'current_password':accounts['forced']['password'],'new_password':'x'*9},headers={'Origin':origin,'X-CSRF-Token':me['csrf_token']})
            check(rejected.status==422,'PASSWORD10 actual production API rejects nine characters')
            changed='test-next2'
            PRIVATE_PASSWORDS.extend([accounts['forced']['password'],changed])
            forced.locator('input[name=current_password]').fill(accounts['forced']['password'])
            forced.locator('input[name=new_password]').fill(changed)
            forced.locator('input[name=confirm_password]').fill(changed)
            forced.get_by_role('button',name='保存新密码',exact=True).click()
            expect(forced.get_by_role('heading',name='持续跟踪项目',exact=True)).to_be_visible()
            accounts['forced']['password']=changed
            check(True,'AUTH-03 actual browser forced password change and rotated session')
            check(len(changed)==10,'PASSWORD10 actual production browser accepts ten characters')
            fallback=browser.new_context(java_script_enabled=False)
            fallback.add_cookies(forced_context.cookies())
            no_password_js=fallback.new_page();requests=[]
            no_password_js.on('request',lambda r:requests.append((r.method,r.url)))
            no_password_js.goto(origin+'/auth/password')
            no_password_js.locator('input[name=current_password]').fill(changed)
            no_password_js.locator('input[name=new_password]').fill('Fictional-C0-NoJS-New-Password')
            no_password_js.locator('input[name=confirm_password]').fill('Fictional-C0-NoJS-New-Password')
            with no_password_js.expect_navigation() as navigation:
                no_password_js.get_by_role('button',name='保存新密码',exact=True).click()
            check(navigation.value.status==415 and requests[-1][0]=='POST' and all(changed not in url and 'Fictional-C0-NoJS' not in url for _,url in requests),'AUTH-03 actual no-JS password form uses safe POST')
            fallback.close();forced_context.close()
            for width in (1440,390):
                context=browser.new_context(viewport={'width':width,'height':1000})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(type(error).__name__))
                def login(role):
                    page.goto(origin+'/login')
                    page.locator('input[name=username]').fill(accounts[role]['username'])
                    page.locator('input[name=password]').fill(accounts[role]['password'])
                    page.get_by_role('button',name='登录',exact=True).click()
                    expect(page.get_by_role('heading',name='持续跟踪项目',exact=True)).to_be_visible()
                login('admin')
                populated(page,'admin',width,output,check)
                expect(page.locator('.ik-nav-link[href="/tracking"]')).to_have_accessible_name('猎手项目追踪')
                expect(page.locator('.ik-nav-link[href="/tracking"]')).to_contain_text('猎手项目追踪')
                check(True,'owner-approved tracking navigation wording',width=width)
                page.get_by_label('下一页',exact=True).click()
                expect(page.locator('.hpv2-table-footer')).to_contain_text('显示 10–18 条')
                expect(page.get_by_label('第 3 页',exact=True)).to_be_enabled()
                check(True,'browser known cursor navigation',width=width)
                page.get_by_label('搜索项目',exact=True).fill('C0验收项目112')
                expect(page.locator('.hpv2-table-footer')).to_contain_text('共 1 条')
                expect(page.locator('.hpv2-events tbody tr')).not_to_have_count(0)
                check(True,'browser important events independent of main search',width=width)
                page.get_by_role('button',name='＋ 新增项目',exact=True).click()
                name=f'C0浏览器新增{width}'
                page.get_by_label('项目名称',exact=True).fill(name)
                page.get_by_role('button',name='保存资料',exact=True).click()
                expect(page.get_by_role('dialog')).to_have_count(0)
                page.get_by_label('搜索项目',exact=True).fill(name)
                row=page.locator('.hpv2-projects tbody tr').filter(has_text=name)
                expect(row).to_be_visible()
                page.reload();page.get_by_label('搜索项目',exact=True).fill(name);expect(row).to_be_visible()
                check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'browser no whole-page overflow',width=width)
                page.screenshot(path=str(output/f'homepage-{width}.png'),full_page=True)
                row.get_by_role('button',name='编辑',exact=True).click()
                page.get_by_label('备注',exact=True).fill('浏览器持久化备注')
                page.get_by_role('button',name='保存资料',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
                row.get_by_role('button',name='移除',exact=True).click()
                page.get_by_role('button',name='标记完成并移除',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
                page.get_by_role('button',name=re.compile('已完成记录')).click()
                while not page.locator('.hpv2-record-row').filter(has_text=name).count():
                    previous=page.locator('.hpv2-record-row > div > strong').first.inner_text()
                    page.get_by_label('下一页记录',exact=True).click()
                    expect(page.locator('.hpv2-record-row > div > strong').first).not_to_have_text(previous)
                page.locator('.hpv2-record-row').filter(has_text=name).get_by_role('button',name='恢复跟踪',exact=True).click()
                expect(page.get_by_role('dialog')).to_have_attribute('aria-busy','false')
                page.get_by_role('dialog').get_by_role('button',name='关闭弹窗',exact=True).click()
                expect(row).to_be_visible()
                check(True,'browser CRUD, refresh, completion and restore',width=width)
                for route in ('hunter','tracking'):
                    page.goto(origin+'/'+route);expect(page.get_by_text('未接入。',exact=False)).to_be_visible()
                context.close()
                readonly=browser.new_context(viewport={'width':width,'height':1000});page=readonly.new_page()
                login('user')
                populated(page,'user',width,output,check)
                check(page.get_by_role('button',name='＋ 新增项目',exact=True).count()==0,'AUTH-02 actual UI read-only write entry hidden',width=width)
                page.screenshot(path=str(output/f'readonly-{width}.png'),full_page=True)
                readonly.close()
                check(not errors,'browser no page errors',width=width)
            nojs=browser.new_context(java_script_enabled=False)
            page=nojs.new_page();requests=[];page.on('request',lambda r:requests.append((r.method,r.url)))
            page.goto(origin+'/login');page.locator('input[name=username]').fill('fictional_nojs')
            fake='Fictional-C0-NoJS-Password';page.locator('input[name=password]').fill(fake)
            with page.expect_navigation() as navigation:
                page.get_by_role('button',name='登录',exact=True).click()
            check(navigation.value.status==415 and requests[-1][0]=='POST' and all(fake not in url for _,url in requests),'AUTH-01 actual no-JS password uses safe POST')
            nojs.close()
        finally:
            browser.close()


def backups(data_root, work):
    result={}
    for name in ('auth','projects'):
        source=data_root/name/(name+'.db');target=work/'restored'/name/(name+'.db')
        target.parent.mkdir(parents=True,mode=0o700)
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(target) as dst:
            src.backup(dst);dst.execute('PRAGMA journal_mode=DELETE')
            check(dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok','ISO-01 backup integrity',domain=name)
            check(not dst.execute('PRAGMA foreign_key_check').fetchall(),'ISO-01 backup foreign keys',domain=name)
        target.chmod(0o600)
        check(db_fingerprint(source)==db_fingerprint(target),'ISO-01 restored logical database equals source',domain=name)
        result[name]={'restored_path':str(target),'sha256':digest(target),'live_data_replaced':False}
    return result


def legacy_account(data_root, origin):
    """Use frozen hash code only on this disposable DB, never on the deployed data."""
    password=secrets.token_urlsafe(24);PRIVATE_PASSWORDS.append(password)
    cli(data_root,origin,'create','c0_legacy',password)
    source=subprocess.check_output(['git','show','28e6aaf4141790fc74ae4ae4429be4b854460955:modules/auth/src/security.ts'],cwd=ROOT,text=True)
    code="""import ts from 'typescript';import {readFileSync} from 'node:fs';
const x=JSON.parse(readFileSync(0,'utf8'));
const js=ts.transpileModule(x.source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const frozen=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
process.stdout.write(await frozen.hashPassword(x.password));"""
    hashed=subprocess.check_output([str(NODE),'--input-type=module','-e',code],cwd=ROOT,input=json.dumps({'source':source,'password':password}),text=True)
    with sqlite3.connect(data_root/'auth/auth.db') as con:
        con.execute('UPDATE auth_users SET password_hash=?,must_change_password=0 WHERE username=?',(hashed,'c0_legacy'))
    return {'username':'c0_legacy','password':password}


def legacy_login(origin,data_root,account):
    with sqlite3.connect(data_root/'auth/auth.db') as con:
        before=con.execute('SELECT password_hash,version,must_change_password FROM auth_users WHERE username=?',(account['username'],)).fetchone()
    client=httpx.Client(base_url=origin,trust_env=False,timeout=12)
    response=client.post('/api/v1/auth/login',json=account,headers={'Origin':origin})
    check(response.status_code==200 and not response.json()['data']['must_change_password'],'PASSWORD10 actual production accepts frozen fifteen-plus hash')
    with sqlite3.connect(data_root/'auth/auth.db') as con:
        after=con.execute('SELECT password_hash,version,must_change_password FROM auth_users WHERE username=?',(account['username'],)).fetchone()
    check(before==after,'PASSWORD10 frozen hash/version/change flag unchanged after login')
    check(client.post('/api/v1/projects',json={},headers=write_headers(origin,response.json()['data']['csrf_token'])).status_code==403,'PASSWORD10 legacy reader permissions preserved')
    return client


def main():
    work=Path(tempfile.mkdtemp(prefix='ikun-c0-p0-',dir='/private/tmp'))
    with socket.socket() as candidate:
        candidate.bind(('127.0.0.1',0));port=candidate.getsockname()[1]
    origin=f'http://127.0.0.1:{port}';data=work/'data';credentials=work/'synthetic.secret.json'
    report={'started_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'status':'FAIL','origin':origin,
            'scope':'actual received Next production build, synthetic isolated data','public_access_verified':False,
            'workers_started':False,'runtime':str(work),'p0_ids':['AUTH-01','AUTH-02','AUTH-03','PRO-01','PRO-02','ISO-01']}
    process=None;log=None;accounts={}
    out=OUTPUT/('p0-'+str(int(time.time()*1000)))
    out.mkdir(parents=True,exist_ok=False)
    try:
        accounts=provision(data,origin,credentials);PRIVATE_PASSWORDS.extend(x['password'] for x in accounts.values());migrate_projects(data)
        cli(data,origin,'create','c0_rejected','x'*9,expected=1)
        with sqlite3.connect(data/'auth/auth.db') as con:
            check(con.execute('SELECT count(*) FROM auth_users WHERE username=?',('c0_rejected',)).fetchone()[0]==0,'PASSWORD10 real CLI nine rejected without account creation')
        legacy=legacy_account(data,origin)
        for name in ('hunter','tracking'):(data/name).mkdir(mode=0o700)
        sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        env={**environment(data,origin),'PROJECTS_PYTHON':str(PYTHON),'PORT':str(port),'IKUN_RELEASE_SHA':sha}
        log=(work/'website.log').open('w')
        process=subprocess.Popen([str(NODE),str(ROOT/'scripts/start-c0-lite.mjs')],cwd=ROOT,env=env,stdout=log,stderr=log)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('NEXT_START_FAILED')
            try:
                if httpx.get(origin+'/health/ready',trust_env=False).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.2)
        else:raise RuntimeError('NEXT_READY_TIMEOUT')
        empty_store(origin,accounts,out,check,activate)
        seed_projects(data)
        http_p0(origin,data,accounts)
        browsers(origin,accounts,out)
        session=legacy_login(origin,data,legacy)
        try:
            process.terminate();process.wait(timeout=20)
            process=subprocess.Popen([str(NODE),str(ROOT/'scripts/start-c0-lite.mjs')],cwd=ROOT,env=env,stdout=log,stderr=log)
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if process.poll() is not None:raise RuntimeError('NEXT_RESTART_FAILED')
                try:
                    if httpx.get(origin+'/health/ready',trust_env=False).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.2)
            else:raise RuntimeError('NEXT_RESTART_TIMEOUT')
            check(session.get('/api/v1/auth/me').status_code==200 and session.get('/api/v1/projects').status_code==200,'PASSWORD10 existing legacy session survives actual production restart')
        finally:
            session.close()
        report['backup_restore']=backups(data,work)
        report['build']={'tested_git_head':sha,'next_build_id':(ROOT/'apps/website/.next/BUILD_ID').read_text().strip(),
                         'lock_sha256':digest(ROOT/'pnpm-lock.yaml')}
        report['status']='PASS'
    except Exception as error:
        message=str(error)
        for account in accounts.values():
            message=message.replace(account['password'],'<redacted>')
        for password in PRIVATE_PASSWORDS:
            message=message.replace(password,'<redacted>')
        report['error_type']=type(error).__name__;report['reason']=message[:1500]
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=20)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        if log:log.close()
        report['checks']=CHECKS;report['passed_checks']=sum(x['result']=='PASS' for x in CHECKS)
        report['owned_website_stopped']=process is None or process.poll() is not None
        report['finished_at']=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
        (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'status':report['status'],'checks':report['passed_checks'],'report':str(out/'result.json'),
                          'reason':report.get('reason')},ensure_ascii=False))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    sys.exit(main())
