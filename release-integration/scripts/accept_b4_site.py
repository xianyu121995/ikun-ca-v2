#!/usr/bin/env python3
"""Actual production Next + independent frozen Hunter, synthetic isolated data only."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import httpx
from c0_test_fixture import ROOT, NODE, PYTHON, environment, provision, migrate_projects, cli

OUT = ROOT / 'release-integration/.runtime/night-b4'
CHECKS = []


def check(value, name):
    CHECKS.append({'check': name, 'result': 'PASS' if value else 'FAIL'})
    if not value:
        raise AssertionError(name)


def port():
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        return server.getsockname()[1]


def wait_ready(origin, process):
    deadline = time.monotonic() + 25
    with httpx.Client(trust_env=False, timeout=1) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('ISOLATED_PROCESS_EXITED')
            try:
                response = client.get(origin + '/health/ready')
                if response.status_code == 200:
                    return response.json()['data']
            except httpx.HTTPError:
                pass
            time.sleep(.15)
    raise RuntimeError('ISOLATED_READINESS_TIMEOUT')


def login(client, origin, account):
    response = client.post('/api/v1/auth/login', json=account, headers={'Origin': origin})
    check(response.status_code == 200, 'real_auth_login_' + account['username'])
    data = response.json()['data']
    if data['must_change_password']:
        new = secrets.token_urlsafe(24)
        changed = client.post('/api/v1/auth/password', json={'current_password': account['password'], 'new_password': new},
                              headers={'Origin': origin, 'X-CSRF-Token': data['csrf_token']})
        check(changed.status_code == 200, 'real_first_password_change_' + account['username'])
        account['password'] = new
    return client.get('/api/v1/auth/me').json()['data']


def seed_hunter(data):
    sys.path.insert(0, str(ROOT / 'services/hunter-worker/python'))
    from hunterradar.store import Store
    from hunterradar.parsers import Follow, Target
    now = time.time()
    store = Store(data / 'hunter/hunter.db', initialize=True)
    for number in (1, 2):
        name = 'c0fhunter' + str(number)
        item = store.add(name, now=now - 300000)
        store.apply_profile(item, str(100 + number), name, 5000, now - 300000)
        store.establish_wss_baseline([store.hunter(item['id'])], now - 300000)
        target = Target('c0fproject', '999001', '本地验收夹具 C0 Hunter', '仅隔离夹具，无真实来源')
        store.ingest_wss(Follow(name, target, now - 60, now, '6551_WSS', 'fixture:' + str(number)))


def main():
    OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='ikun-b4-site-', dir='/private/tmp'))
    data = scratch / 'data'
    origin = 'http://127.0.0.1:' + str(port())
    hunter_origin = 'http://127.0.0.1:' + str(port())
    accounts = provision(data, origin, scratch / 'accounts.private.json')
    migrate_projects(data)
    seed_hunter(data)
    token, ingest = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    env = environment(data, origin)
    env.update(IKUN_RELEASE_SHA=head, PROJECTS_PYTHON=str(PYTHON), PORT=origin.rsplit(':', 1)[1],
               IKUN_HUNTER_ORIGIN=hunter_origin, HUNTER_API_TOKEN=token, PROJECTS_INGEST_HUNTER_TOKEN=ingest)
    worker_env = {**env, 'HUNTER_ENGINE': 'python', 'HUNTER_PYTHON_BIN': str(OUT / 'venv/bin/python'),
                  'HUNTER_HOST': '127.0.0.1', 'HUNTER_PORT': hunter_origin.rsplit(':', 1)[1],
                  'HUNTER_DB': str(data / 'hunter/hunter.db'), 'HUNTER_V2_MODE': '1',
                  'HUNTER_EXTERNAL_IO_ENABLED': '0', 'HUNTER_REQUIRE_EXTERNAL_IO_DISABLED': '1',
                  'HUNTER_PROJECT_DELIVERY_ENABLED': '1', 'HUNTER_DELIVERY_PROTOCOL': 'v2-event',
                  'HUNTER_PROJECT_TASK_URL': origin + '/internal/v1/ingest/hunter'}
    processes = []
    report = {'state': 'RUNNING', 'source_head': head, 'scratch': str(scratch), 'checks': CHECKS,
              'real_provider_calls': 0, 'Tracking_full_chain': 'NOT_RECEIVED_NOT_CLAIMED'}
    log = open(OUT / ('site-' + str(time.time_ns()) + '.log'), 'ab', buffering=0)
    try:
        worker = subprocess.Popen([str(NODE), 'services/hunter-worker/dist/main.js'], cwd=ROOT, env=worker_env,
                                  stdout=log, stderr=log, start_new_session=True)
        processes.append(worker)
        status = wait_ready(hunter_origin, worker)
        check(status['external_io_enabled'] is False and status['source_status'] == '未连接真实来源', 'worker_external_collection_off')
        web = subprocess.Popen([str(NODE), 'scripts/start-c0-lite.mjs'], cwd=ROOT, env=env,
                               stdout=log, stderr=log, start_new_session=True)
        processes.append(web)
        wait_ready(origin, web)
        check(web.pid != worker.pid, 'website_and_hunter_independent_processes')
        admin = httpx.Client(base_url=origin, trust_env=False, timeout=12)
        user = httpx.Client(base_url=origin, trust_env=False, timeout=12)
        anonymous = httpx.Client(base_url=origin, trust_env=False, timeout=12)
        admin_me = login(admin, origin, accounts['admin'])
        user_me = login(user, origin, accounts['user'])
        for route in ('/api/v1/hunter/signals', '/api/v1/hunter/events', '/api/v1/events/stream'):
            check(anonymous.get(route).status_code == 401, 'anonymous_rejected_' + route)
        check(user.get('/api/v1/tracking/events').status_code == 501, 'tracking_unreceived_not_auth_403_or_substituted_stream')
        check(user.get('/api/v1/hunter/events', headers={'Last-Event-ID': 'evt_' + str(uuid.uuid4())}).status_code == 422, 'hunter_rejects_tracking_cursor')
        check(user.get('/api/v1/events/stream', headers={'Last-Event-ID': 'hunter:1'}).status_code == 422, 'projects_rejects_hunter_cursor')
        rows = user.get('/api/v1/hunter/signals').json()['data']['items']
        check(len(rows) == 1, 'synthetic_discovery_public_DTO')
        check('c0fhunter' not in json.dumps(rows), 'ordinary_DTO_no_individual_hunter_identity')
        discovery = rows[0]
        headers = {'Origin': origin, 'X-CSRF-Token': user_me['csrf_token'], 'Idempotency-Key': str(uuid.uuid4()),
                   'If-Match': '"rev-' + str(discovery['revision']) + '"'}
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            check(user.request(method, '/api/v1/hunter/accounts', json={}, headers=headers).status_code == 403, 'user_write_rejected_' + method)
        check(user.get('/api/v1/hunter/accounts').status_code == 403, 'hunter_management_admin_only')
        with user.stream('GET', '/api/v1/hunter/events') as response:
            event_id = None
            for line in response.iter_lines():
                if line.startswith('id: '):
                    event_id = line[4:]
                    break
            check(response.status_code == 200 and event_id and event_id.startswith('hunter:'), 'native_hunter_cursor_preserved')
        with user.stream('GET', '/api/v1/events/stream') as response:
            check(response.status_code == 200, 'original_projects_stream_preserved')
        key = str(uuid.uuid4())
        headers = {'Origin': origin, 'X-CSRF-Token': admin_me['csrf_token'], 'Idempotency-Key': key,
                   'If-Match': '"rev-' + str(discovery['revision']) + '"'}
        path = '/api/v1/hunter/discoveries/' + discovery['discovery_id'] + '/monitoring-requests'
        body = {'confirmed': True, 'project': discovery['project']}
        accepted = admin.post(path, json=body, headers=headers)
        check(accepted.status_code == 202 and accepted.json()['data']['state'] in ('accepted', 'pending'), 'manual_confirmation_durable_not_running')
        command = accepted.json()['data']['command_id']
        repeat = admin.post(path, json=body, headers=headers)
        check(repeat.status_code == 202 and repeat.json()['data']['command_id'] == command, 'same_idempotency_original_command')
        deadline = time.monotonic() + 20
        hidden = []
        while time.monotonic() < deadline:
            response = admin.get('/api/v1/projects?home_membership=hidden')
            hidden = response.json().get('data', {}).get('items', [])
            if hidden:
                break
            time.sleep(.25)
        check(len(hidden) == 1, 'hunter_loopback_delivery_Projects_IPC_canonical_hidden')
        project = hidden[0]
        status = admin.get('/api/v1/commands/' + command)
        check(status.status_code == 503 and status.json()['error']['code'] == 'AUTH_NOT_CONFIGURED', 'canonical_known_tracking_unreceived_honest_503')
        check(not (data / 'tracking/tracking.db').exists(), 'no_unreceived_tracking_database_or_implicit_init')
        project_headers = {'Origin': origin, 'Content-Type': 'application/json', 'X-CSRF-Token': admin_me['csrf_token'], 'Idempotency-Key': str(uuid.uuid4()),
                           'If-Match': '"rev-' + str(project['revision']) + '"'}
        added = admin.post('/api/v1/projects/' + project['project_id'] + '/home-membership', json={'action': 'add'}, headers=project_headers)
        check(added.status_code == 200, 'homepage_add_is_separate_explicit_action')
        check(len(user.get('/api/v1/projects').json()['data']['items']) == 1, 'homepage_public_project_visible')
        before = user.get('/api/v1/hunter/discoveries/' + discovery['discovery_id']).json()['data']
        current = admin.get('/api/v1/projects/' + project['project_id']).json()['data']
        project_headers.update({'Idempotency-Key': str(uuid.uuid4()), 'If-Match': '"rev-' + str(current['revision']) + '"'})
        removed = admin.delete('/api/v1/projects/' + project['project_id'], headers=project_headers)
        check(removed.status_code == 200, 'homepage_remove_only')
        after = user.get('/api/v1/hunter/discoveries/' + discovery['discovery_id']).json()['data']
        check(before == after, 'Projects_remove_does_not_change_Hunter_discovery')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as browser_runtime:
            browser = browser_runtime.chromium.launch(channel='chrome', headless=True)
            try:
                for role in ('admin', 'user'):
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto(origin + '/login')
                    page.locator('input[name="username"]').fill(accounts[role]['username'])
                    page.locator('input[name="password"]').fill(accounts[role]['password'])
                    page.locator('button[type="submit"]').click()
                    page.wait_for_url(origin + '/', timeout=15000)
                    for width in (1440, 390):
                        page.set_viewport_size({'width': width, 'height': 1000})
                        page.goto(origin + '/hunter')
                        page.get_by_text('本地验收夹具 C0 Hunter', exact=False).first.wait_for(timeout=15000)
                        check(page.get_by_text('未连接真实来源', exact=False).count() > 0, f'live_truthful_source_{role}_{width}')
                        check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'), f'layout_no_page_overflow_{role}_{width}')
                        page.screenshot(path=str(OUT / f'hunter-{role}-{width}.png'), full_page=True)
                    context.close()
            finally:
                browser.close()
        started, done = threading.Event(), threading.Event()
        stream_state = {}
        def watch():
            try:
                with httpx.Client(base_url=origin, cookies=user.cookies, trust_env=False, timeout=10) as client:
                    with client.stream('GET', '/api/v1/hunter/events') as response:
                        stream_state['status'] = response.status_code
                        for line in response.iter_lines():
                            if line.startswith('id: '):
                                started.set()
                        stream_state['normal_eof'] = True
            except httpx.HTTPError:
                stream_state['transport_error'] = True
            finally:
                done.set()
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        check(started.wait(5), 'live_user_SSE_started_before_revocation')
        cli(data, origin, 'disable', accounts['user']['username'])
        check(user.get('/api/v1/hunter/signals').status_code == 401, 'disabled_user_API_revoked')
        check(done.wait(6) and stream_state.get('normal_eof'), 'quiet_module_SSE_revoked_without_new_event')
        check(admin.get('/api/v1/auth/me').status_code == 200, 'admin_unaffected_by_synthetic_user_disable')
        report['state'] = 'PASS_B4_LOCAL_NEXT_AND_HUNTER_ONLY'
        report['command_id'] = command
        report['project_id'] = project['project_id']
        report['build_id'] = (ROOT / 'apps/website/.next/BUILD_ID').read_text().strip()
    except Exception as error:
        report['state'] = 'FAIL'
        report['error_type'] = type(error).__name__
        report['error'] = str(error) if isinstance(error, (AssertionError, RuntimeError)) else 'inspect private task log'
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        log.close()
        output = OUT / ('site-acceptance-' + str(time.time_ns()) + '.json')
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        output.chmod(0o600)
        print(json.dumps({'state': report['state'], 'checks': len(CHECKS), 'receipt': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
