"""Whole-page capability regression against the actual production Next service."""
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

WRITE_NAMES = re.compile(r'新增项目|添加项目|编辑|移除|恢复跟踪|加入主页|保存资料|标记完成')


def audit(page, role, width, surface, check):
    expect(page.locator('[data-project-access]')).to_have_attribute('data-project-access', 'readonly' if role == 'user' else 'write')
    if role == 'user':
        controls = page.get_by_role('button', name=WRITE_NAMES, include_hidden=True)
        check(all(controls.nth(i).is_disabled() for i in range(controls.count())), 'READONLY all-page business buttons disabled', width=width, surface=surface)
        check(all(not controls.nth(i).is_visible() for i in range(controls.count())), 'READONLY business affordances hidden', width=width, surface=surface)
        check(page.locator('input[type=checkbox]:enabled').count() == 0, 'READONLY no enabled business selection', width=width, surface=surface)
        check(page.get_by_role('link', name=WRITE_NAMES).count() == 0, 'READONLY no global business write link', width=width, surface=surface)
    else:
        check(True, 'ADMIN trusted write capability retained', width=width, surface=surface)


def populated(page, role, width, output, check):
    """Exercise every reachable presentation surface, including the global page header."""
    writes = []
    page.on('request', lambda request: writes.append(request.method) if request.method not in ('GET', 'HEAD') and '/api/v1/projects' in request.url else None)
    page.get_by_label('搜索项目', exact=True).fill('')
    expect(page.locator('.hpv2-projects tbody tr')).not_to_have_count(0)
    audit(page, role, width, 'homepage/global-header/table', check)
    if role == 'admin':
        expect(page.get_by_role('button', name='＋ 新增项目', exact=True)).to_be_enabled()
        expect(page.locator('.hpv2-projects input[type=checkbox]').first).to_be_enabled()
        page.get_by_label('全选当前页', exact=True).check()
        page.get_by_role('button', name=re.compile('移除已选')).click()
        expect(page.get_by_role('dialog').get_by_role('button', name='标记完成并移除', exact=True)).to_be_enabled()
        page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
        page.get_by_label('全选当前页', exact=True).uncheck()
        check(True, 'ADMIN bulk selection confirmation and cancellation retained', width=width)
    else:
        expect(page.get_by_role('button', name='＋ 新增项目', exact=True)).to_have_count(0)
    page.locator('.hpv2-project-name[data-project-id]').first.click()
    dialog = page.get_by_role('dialog')
    expect(dialog.get_by_role('heading', name='项目资料', exact=True)).to_be_visible()
    audit(page, role, width, 'project-detail', check)
    if role == 'admin':
        expect(dialog.get_by_role('button', name='编辑资料', exact=True)).to_be_enabled()
        expect(dialog.get_by_role('button', name='删除主页条目', exact=True)).to_be_enabled()
        dialog.get_by_role('button', name='删除主页条目', exact=True).click()
        expect(dialog.get_by_role('heading', name='删除主页条目', exact=True)).to_be_visible()
        expect(dialog.get_by_role('button', name='确认移除主页', exact=True)).to_be_enabled()
        dialog.get_by_role('button', name='取消', exact=True).click()
        expect(dialog.get_by_role('heading', name='项目资料', exact=True)).to_be_visible()
        check(True, 'ADMIN detail removal confirmation and cancellation retained', width=width)
    dialog.get_by_role('button', name='关闭弹窗', exact=True).click()
    page.get_by_role('button', name=re.compile('已完成记录')).click()
    expect(dialog.locator('.hpv2-record-row')).not_to_have_count(0)
    audit(page, role, width, 'completed-records', check)
    if role == 'admin':
        expect(dialog.get_by_role('button', name='恢复跟踪', exact=True).first).to_be_enabled()
    dialog.get_by_role('button', name='关闭弹窗', exact=True).click()
    page.get_by_role('button', name=re.compile('其他项目')).click()
    expect(dialog.locator('.hpv2-record-row')).not_to_have_count(0)
    audit(page, role, width, 'other-projects', check)
    join = dialog.get_by_role('button', name='加入主页', exact=True, include_hidden=True)
    expect(join.first).to_have_count(1)
    if role == 'admin':
        expect(join.first).to_be_enabled()
        expect(dialog.get_by_role('button', name='编辑', exact=True).first).to_be_enabled()
    else:
        check(all(join.nth(i).is_disabled() and not join.nth(i).is_visible() for i in range(join.count())), 'READONLY membership join denied', width=width)
    expect(dialog.get_by_role('button', name='查看资料', exact=True).first).to_be_enabled()
    dialog.get_by_role('button', name='关闭弹窗', exact=True).click()
    page.locator('summary').click()
    expect(page.get_by_role('link', name='修改本人密码', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='退出登录', exact=True)).to_be_enabled()
    audit(page, role, width, 'account-menu', check)
    page.locator('summary').click()
    page.get_by_label('搜索项目', exact=True).fill('C0-no-result-readonly-audit')
    expect(page.get_by_text('没有符合条件的项目', exact=True)).to_be_visible()
    audit(page, role, width, 'search-empty-state', check)
    if role == 'admin':
        expect(page.get_by_role('button', name='＋ 新增项目', exact=True)).to_be_enabled()
    expect(page.get_by_label('搜索项目', exact=True)).to_be_enabled()
    expect(page.get_by_label('评分筛选').get_by_role('button').first).to_be_enabled()
    page.screenshot(path=str(output / f'entry-{role}-empty-{width}.png'), full_page=True)
    page.get_by_label('搜索项目', exact=True).fill('')
    expect(page.locator('.hpv2-projects tbody tr')).not_to_have_count(0)
    if role == 'user':
        page.get_by_label('下一页', exact=True).click()
        expect(page.locator('.hpv2-table-footer')).to_contain_text('显示 10–18 条')
        check(not writes, 'READONLY navigation emits no business write request', width=width)
    check(True, 'read-only search filters pagination and viewing retained', width=width, role=role)


def empty_store(origin, accounts, output, check, activate):
    """Real empty Projects DB, before seeding; no request interception or mock responses."""
    import httpx
    for role in ('admin', 'user'):
        with httpx.Client(base_url=origin, trust_env=False, timeout=12) as client:
            activate(client, origin, accounts[role])
    candidates = sorted(Path.home().glob('Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(candidates[-1]), headless=True)
        try:
            for width in (1440, 390):
                for role in ('admin', 'user'):
                    context = browser.new_context(viewport={'width': width, 'height': 1000})
                    page = context.new_page()
                    page.goto(origin + '/login')
                    page.locator('input[name=username]').fill(accounts[role]['username'])
                    page.locator('input[name=password]').fill(accounts[role]['password'])
                    page.get_by_role('button', name='登录', exact=True).click()
                    expect(page.get_by_text('没有符合条件的项目', exact=True)).to_be_visible()
                    me = context.request.get(origin + '/api/v1/auth/me').json()['data']
                    check(me['role'] == ('user' if role == 'user' else 'superadmin'), 'server session role matches tested browser', width=width, role=role)
                    audit(page, role, width, 'genuine-empty-database', check)
                    if role == 'admin':
                        expect(page.get_by_role('button', name='＋ 新增项目', exact=True)).to_be_enabled()
                    page.screenshot(path=str(output / f'entry-{role}-empty-db-{width}.png'), full_page=True)
                    context.close()
        finally:
            browser.close()
