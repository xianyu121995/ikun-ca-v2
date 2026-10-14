"""Real Chromium + real HTTP + temporary projects.db. No production services."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

from projects_service.db import Database, create_project
from projects_service.models import ProjectFields


class ServerFixture(dict):
    def __repr__(self):
        return f"ServerFixture(origin={self['origin']!r}, credentials=<redacted>)"


@pytest.fixture
def server(tmp_path):
    db = Database(tmp_path/'projects.db')
    db.migrate()
    admin_id, admin = db.create_principal('superadmin')
    _, viewer = db.create_principal('user')
    for i in range(23):
        with db.transaction() as con:
            create_project(con, ProjectFields(name=f'Fixture {i:02d}', rating=['S','A','B'][i%3],
                                              website=f'https://project-{i}.example', description='隔离测试资料',
                                              progress='watching' if i%2 else 'todo',
                                              token_date='2099-12-31' if i<3 else None,
                                              token_date_status='estimated' if i<3 else 'unconfirmed'), admin_id, f'fixture-key-{i}')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    log = (tmp_path/'server.log').open('w')
    process = subprocess.Popen([sys.executable,'-m','projects_service','--db',str(db.path),'serve','--port',str(port)],
                               env={**os.environ,'PROJECTS_ORIGIN':origin}, stdout=log, stderr=log)
    try:
        for _ in range(100):
            try:
                if httpx.get(origin+'/healthz').status_code == 200: break
            except httpx.ConnectError:
                pass
            if process.poll() is not None:
                raise AssertionError((tmp_path/'server.log').read_text())
            time.sleep(.05)
        else: raise AssertionError('Test server did not start')
        yield ServerFixture(origin=origin,superadmin=admin,user=viewer,db=db)
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill();process.wait()
        log.close()


@pytest.fixture
def browser_page():
    with sync_playwright() as playwright:
        executable = os.environ.get('PROJECTS_TEST_CHROMIUM')
        # Existing local Chromium is sufficient; no browser download is needed.
        if not executable:
            candidates = sorted((Path.home()/'Library/Caches/ms-playwright').glob('chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'))
            executable = str(candidates[-1]) if candidates else None
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        context = browser.new_context(viewport={'width':1440,'height':1000}, timezone_id='Asia/Shanghai')
        page = context.new_page()
        yield page
        context.close()
        browser.close()


def login(page, server, role='superadmin'):
    page.goto(server['origin'])
    page.get_by_label('访问凭证', exact=True).fill(server[role])
    page.get_by_role('button',name='登录',exact=True).click()
    expect(page.locator('#login-dialog')).not_to_be_visible()
    expect(page.locator('#page-info')).to_contain_text('共 23 个项目')


def test_browser_crud_persistence_and_no_script_execution(server, browser_page):
    page = browser_page
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    login(page,server)
    page.get_by_role('button',name='新建项目').click()
    form=page.locator('#editor-form')
    form.get_by_label('项目名称',exact=True).fill('真实 CRUD 验收')
    form.get_by_label('评分',exact=True).select_option('S')
    form.get_by_label('官网',exact=True).fill('https://acceptance.example')
    form.get_by_label('简介',exact=True).fill('<img src=x onerror="window.injected=1">')
    form.get_by_label('备注',exact=True).fill('首次记录')
    form.get_by_label('研究进度',exact=True).select_option('researching')
    form.get_by_label('发币日期',exact=True).fill('2099-06-30')
    form.get_by_label('日期状态',exact=True).select_option('estimated')
    form.get_by_role('button',name='保存项目').click()
    expect(page.locator('#editor-dialog')).not_to_be_visible()
    row=page.locator('#rows tr').filter(has_text='真实 CRUD 验收')
    expect(row).to_be_visible()
    project_id=row.get_attribute('data-project-id')
    expect(row).to_contain_text('首次记录')
    assert page.evaluate('window.injected') is None
    assert row.locator('img').count()==0
    row.get_by_role('button',name='编辑 真实 CRUD 验收',exact=True).click()
    form.get_by_label('备注',exact=True).fill('第二次记录')
    form.get_by_label('研究进度',exact=True).select_option('completed')
    form.get_by_role('button',name='保存项目').click()
    expect(row).to_contain_text('第二次记录')
    page.reload()
    expect(page.locator('#page-info')).to_contain_text('共 24 个项目')
    expect(page.locator(f'tr[data-project-id="{project_id}"]')).to_contain_text('第二次记录')
    row=page.locator(f'tr[data-project-id="{project_id}"]')
    row.get_by_role('button',name='删除 真实 CRUD 验收',exact=True).click()
    page.get_by_role('button',name='确认删除',exact=True).click()
    expect(page.locator('#delete-dialog')).not_to_be_visible()
    expect(page.locator('#page-info')).to_contain_text('共 23 个项目')
    expect(page.locator(f'tr[data-project-id="{project_id}"]')).to_have_count(0)
    with server['db'].connect() as con:
        row=con.execute('SELECT deleted_at,version FROM projects WHERE id=?',(project_id,)).fetchone()
        assert row['deleted_at'] and row['version']==3
    assert not errors


def test_browser_search_filters_sort_pagination_times(server,browser_page):
    page=browser_page
    login(page,server)
    expect(page.locator('#rows tr')).to_have_count(20)
    page.get_by_role('button',name='下一页 →',exact=True).click()
    expect(page.locator('#rows tr')).to_have_count(3)
    page.get_by_role('button',name='← 上一页',exact=True).click()
    expect(page.locator('#rows tr')).to_have_count(20)
    page.get_by_role('button',name='S级',exact=True).click()
    expect(page.locator('#rows tr')).to_have_count(8)
    page.get_by_label('研究进度筛选').select_option('watching')
    expect(page.locator('#rows tr')).to_have_count(4)
    page.get_by_role('button',name='全部',exact=True).click()
    page.get_by_label('研究进度筛选').select_option('')
    page.get_by_label('搜索持续跟踪项目').fill('Fixture 00')
    expect(page.locator('#rows tr')).to_have_count(1)
    page.get_by_label('搜索持续跟踪项目').fill('不存在项目')
    expect(page.locator('#empty')).to_be_visible()
    expect(page.locator('#rows tr')).to_have_count(0)
    page.get_by_label('搜索持续跟踪项目').fill('')
    page.get_by_label('项目排序').select_option('name')
    expect(page.locator('#rows tr').first).to_contain_text('Fixture 00')
    page.get_by_label('每页数量').select_option('50')
    expect(page.locator('#rows tr')).to_have_count(23)
    page.get_by_role('button',name='查看全部 →',exact=True).click()
    expect(page.locator('#times-list article')).to_have_count(3)
    page.get_by_role('button',name='关闭重要时间',exact=True).click()
    page.get_by_role('button',name='退出',exact=True).click()
    expect(page.locator('#login-dialog')).to_be_visible()
    expect(page.locator('#rows tr')).to_have_count(0)


@pytest.mark.parametrize('role,can_create,can_edit', [('user',False,False)])
def test_browser_role_controls(server,browser_page,role,can_create,can_edit):
    page=browser_page
    login(page,server,role)
    assert page.get_by_role('button',name='新建项目').is_enabled()==can_create
    assert (page.get_by_role('button',name='编辑 Fixture 22',exact=True).count()>0)==can_edit
    assert page.get_by_role('button',name='删除 Fixture 22',exact=True).count()==0


def test_browser_duplicate_conflict_and_error_feedback(server,browser_page):
    page=browser_page
    login(page,server)
    page.get_by_role('button',name='新建项目').click()
    form=page.locator('#editor-form')
    form.get_by_label('项目名称',exact=True).fill('重复项目')
    form.get_by_label('官网',exact=True).fill('https://project-0.example')
    form.get_by_role('button',name='保存项目').click()
    expect(page.locator('#editor-error')).to_contain_text('该官网已存在')
    expect(page.locator('#editor-dialog')).to_be_visible()
    page.get_by_role('button',name='取消',exact=True).click()
    page.get_by_role('button',name='编辑 Fixture 22',exact=True).click()
    form.get_by_label('备注',exact=True).fill('我的修改')
    project_id=page.locator('#rows tr').filter(has_text='Fixture 22').get_attribute('data-project-id')
    with server['db'].transaction() as con:
        con.execute('UPDATE projects SET notes=?,version=version+1 WHERE id=?',('其他人的修改',project_id))
    form.get_by_role('button',name='保存项目').click()
    expect(page.locator('#editor-error')).to_contain_text('项目已被修改')
    expect(form.get_by_label('备注',exact=True)).to_have_value('我的修改')


@pytest.mark.parametrize('width',[390,1440,1680,2560])
def test_browser_responsive_layout(server,browser_page,width):
    page=browser_page
    page.set_viewport_size({'width':width,'height':1000})
    login(page,server)
    expect(page.locator('main>section')).to_have_count(3)
    expect(page.locator('thead th')).to_have_count(8)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert page.locator('#project-table').evaluate('(el)=>el.scrollWidth>=el.clientWidth')
    if width==1440:
        target=os.environ.get('PROJECTS_TEST_SCREENSHOT')
        if target: page.screenshot(path=target,full_page=True)
