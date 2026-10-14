"""Isolated Next.js transport smoke; never installs a proxy in the actual website."""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from projects_service.db import Database


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def main():
    module=Path(__file__).resolve().parent.parent
    repo=module.parents[2]
    next_cli=repo/'apps/website/node_modules/next/dist/bin/next'
    if not next_cli.is_file():
        raise RuntimeError('先在本 Worktree 执行 pnpm install --frozen-lockfile')
    node=os.environ.get('PROJECTS_TEST_NODE') or shutil.which('node')
    processes=[]
    with tempfile.TemporaryDirectory(prefix='ikun-next-projects-',dir='/private/tmp') as folder:
        root=Path(folder)
        db=Database(root/'data/projects.db');db.migrate()
        _,admin=db.create_principal('superadmin')
        _,user=db.create_principal('user')
        backend_port,web_port=port(),port()
        origin=f'http://127.0.0.1:{web_port}'
        backend=f'http://127.0.0.1:{backend_port}'
        web=root/'next';(web/'app').mkdir(parents=True)
        (web/'package.json').write_text(json.dumps({'name':'isolated-projects-proxy-test','private':True,'type':'module'}))
        (web/'app/page.jsx').write_text('export default function Page(){return <main>fallback</main>}')
        (web/'app/layout.jsx').write_text('export default function Layout({children}){return <html><body>{children}</body></html>}')
        (web/'next.config.mjs').write_text('export default {experimental:{cpus:1}};')
        shutil.copyfile(module/'integration/next-proxy.js',web/'proxy.js')
        # Same Worktree's installed dependencies only; never use another window's node_modules.
        (web/'node_modules').symlink_to(repo/'apps/website/node_modules',target_is_directory=True)
        log=(root/'services.log').open('w')
        try:
            processes.append(subprocess.Popen([sys.executable,'-m','projects_service','--db',str(db.path),'serve','--port',str(backend_port)],
                cwd=module,env={**os.environ,'PROJECTS_ORIGIN':origin,'PROJECTS_PROXY_AUTHORITY':f'127.0.0.1:{backend_port}'},stdout=log,stderr=log,start_new_session=True))
            processes.append(subprocess.Popen([node,str(next_cli),'dev',str(web),'--webpack','--hostname','127.0.0.1','--port',str(web_port)],
                cwd=web,env={**os.environ,'PROJECTS_API_URL':backend,'PROJECTS_PUBLIC_ORIGIN':origin,'NEXT_TELEMETRY_DISABLED':'1'},
                stdout=log,stderr=log,start_new_session=True))
            with httpx.Client(timeout=5,trust_env=False) as client:
                last_response=None
                for _ in range(100):
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError('临时服务启动失败；检查临时 services.log')
                    try:
                        response=client.get(origin)
                        last_response=response
                        if response.status_code==200 and '登录项目主页' in response.text:break
                    except httpx.TransportError:pass
                    time.sleep(.2)
                else:
                    diagnostic=(root/'services.log').read_text()[-5000:]
                    status=last_response.status_code if last_response is not None else 'no_response'
                    payload=last_response.text[:300] if last_response is not None else ''
                    raise AssertionError(f'Next proxy did not become ready status={status} response={payload}; log={diagnostic}')
                assert client.get(origin+'/api/home/projects').status_code==401
                assert client.get(origin+'/api/home/projects',headers={'Authorization':'Bearer '+user}).status_code==200
                assert client.post(origin+'/api/home/projects',json={'name':'禁止'},headers={'Authorization':'Bearer '+user,'Idempotency-Key':'deny-write-test'}).status_code==403
            with sync_playwright() as playwright:
                candidates=sorted((Path.home()/'Library/Caches/ms-playwright').glob('chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'))
                browser=playwright.chromium.launch(headless=True,executable_path=os.environ.get('PROJECTS_TEST_CHROMIUM') or (str(candidates[-1]) if candidates else None))
                try:
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    page.goto(origin)
                    page.get_by_label('访问凭证',exact=True).fill(admin)
                    page.get_by_role('button',name='登录',exact=True).click()
                    expect(page.locator('#login-dialog')).not_to_be_visible()
                    page.get_by_role('button',name='新建项目').click()
                    page.locator('#editor-form').get_by_label('项目名称',exact=True).fill('Next 代理真实写入')
                    page.get_by_role('button',name='保存项目').click()
                    expect(page.locator('#rows tr')).to_contain_text('Next 代理真实写入')
                    page.reload()
                    expect(page.locator('#rows tr')).to_contain_text('Next 代理真实写入')
                    page.get_by_role('button',name='删除 Next 代理真实写入',exact=True).click()
                    page.get_by_role('button',name='确认删除',exact=True).click()
                    expect(page.locator('#rows tr')).to_have_count(0)
                    page.get_by_role('button',name='退出',exact=True).click()
                    expect(page.locator('#login-dialog')).to_be_visible()
                finally:browser.close()
            with db.connect() as con:
                assert con.execute('SELECT COUNT(*) FROM projects WHERE deleted_at IS NOT NULL').fetchone()[0]==1
            print(json.dumps({'next_proxy_smoke':'passed','real_browser':True,'temporary_projects_db':True,'formal_website_modified':False}))
        finally:
            for process in processes:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
            for process in processes:
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
            log.close()


if __name__=='__main__':main()
