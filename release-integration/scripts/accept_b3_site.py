#!/usr/bin/env python3
"""Actual production Next + two independent frozen workers; offline synthetic intake only."""
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

OUT = ROOT / 'release-integration/.runtime/night-b3'
TRACKING_PYTHON = OUT / 'venv/bin/python'
HUNTER_PYTHON = ROOT / 'release-integration/.runtime/night-b4/venv/bin/python'
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
    scratch = Path(tempfile.mkdtemp(prefix='ikun-b3-site-', dir='/private/tmp'))
    data = scratch / 'data'
    origin = 'http://127.0.0.1:' + str(port())
    hunter_origin = 'http://127.0.0.1:' + str(port())
    tracking_origin = 'http://127.0.0.1:' + str(port())
    accounts = provision(data, origin, scratch / 'accounts.private.json')
    migrate_projects(data)
    seed_hunter(data)
    token, ingest, tracking_token = (secrets.token_urlsafe(32) for _ in range(3))
    tracking_config = scratch / 'tracking.json'
    tracking_config.write_text(json.dumps({'db_path': str(data / 'tracking/tracking.db'), 'remote_enabled': False, 'dedicated_account': False, 'host': '127.0.0.1', 'port': int(tracking_origin.rsplit(':',1)[1])}))
    tracking_config.chmod(0o600)
    init = subprocess.run([str(TRACKING_PYTHON), str(ROOT / 'services/tracking-worker/python/entry.py'), 'init', '--config', str(tracking_config)], capture_output=True, env=environment(data, origin))
    check(init.returncode == 0, 'explicit_tracking_init_before_serve')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    env = environment(data, origin)
    env.update(IKUN_RELEASE_SHA=head, PROJECTS_PYTHON=str(PYTHON), PORT=origin.rsplit(':', 1)[1],
               IKUN_HUNTER_ORIGIN=hunter_origin, HUNTER_API_TOKEN=token, PROJECTS_INGEST_HUNTER_TOKEN=ingest,
               TRACKING_API_URL=tracking_origin, TRACKING_API_TOKEN=tracking_token, IKUN_TRACKING_FIXTURE='1')
    worker_env = {**env, 'HUNTER_ENGINE': 'python', 'HUNTER_PYTHON_BIN': str(HUNTER_PYTHON),
                  'HUNTER_HOST': '127.0.0.1', 'HUNTER_PORT': hunter_origin.rsplit(':', 1)[1],
                  'HUNTER_DB': str(data / 'hunter/hunter.db'), 'HUNTER_V2_MODE': '1',
                  'HUNTER_EXTERNAL_IO_ENABLED': '0', 'HUNTER_REQUIRE_EXTERNAL_IO_DISABLED': '1',
                  'HUNTER_PROJECT_DELIVERY_ENABLED': '1', 'HUNTER_DELIVERY_PROTOCOL': 'v2-event',
                  'HUNTER_PROJECT_TASK_URL': origin + '/internal/v1/ingest/hunter'}
    tracking_env = {**environment(data, origin), 'TRACKING_API_TOKEN': tracking_token, 'IKUN_TRACKING_CONFIG': str(tracking_config), 'IKUN_TRACKING_PYTHON': str(TRACKING_PYTHON), 'IKUN_TRACKING_EXTERNAL_IO_DISABLED': '1'}
    processes = []
    report = {'state': 'RUNNING', 'source_head': head, 'scratch': str(scratch), 'checks': CHECKS,
              'real_provider_calls': 0, 'tracking_intake': 'offline normalized fixture; no remote receipt claimed', 'Projects_tracking_observation_ingest': '501 remains unimplemented', 'audio_output': 'not invoked'}
    log = open(OUT / ('site-' + str(time.time_ns()) + '.log'), 'ab', buffering=0)
    try:
        tracking = subprocess.Popen([str(NODE), 'services/tracking-worker/dist/main.js'], cwd=ROOT, env=tracking_env, stdout=log, stderr=log, start_new_session=True)
        processes.append(tracking)
        wait_ready(tracking_origin, tracking)
        worker = subprocess.Popen([str(NODE), 'services/hunter-worker/dist/main.js'], cwd=ROOT, env=worker_env,
                                  stdout=log, stderr=log, start_new_session=True)
        processes.append(worker)
        status = wait_ready(hunter_origin, worker)
        check(status['external_io_enabled'] is False and status['source_status'] == '未连接真实来源', 'worker_external_collection_off')
        web = subprocess.Popen([str(NODE), 'scripts/start-c0-lite.mjs'], cwd=ROOT, env=env,
                               stdout=log, stderr=log, start_new_session=True)
        processes.append(web)
        ready = wait_ready(origin, web)
        check(ready['workers_enabled'] and all(ready['workers'][key]['configured'] for key in ('hunter','tracking')), 'readiness_reports_configuration_only')
        check(len({tracking.pid, worker.pid, web.pid}) == 3, 'three_independent_processes')
        check(web.pid != worker.pid, 'website_and_hunter_independent_processes')
        admin = httpx.Client(base_url=origin, trust_env=False, timeout=12)
        user = httpx.Client(base_url=origin, trust_env=False, timeout=12)
        anonymous = httpx.Client(base_url=origin, trust_env=False, timeout=12)
        admin_me = login(admin, origin, accounts['admin'])
        user_me = login(user, origin, accounts['user'])
        for route in ('/api/v1/hunter/signals', '/api/v1/hunter/events', '/api/v1/events/stream', '/api/v1/tracking/subscriptions', '/api/v1/tracking/events'):
            check(anonymous.get(route).status_code == 401, 'anonymous_rejected_' + route)
        check(user.get('/api/v1/tracking/events', headers={'Last-Event-ID':'hunter:1'}).status_code == 422, 'tracking_rejects_hunter_cursor')
        for method in ('POST','PATCH','DELETE'):
            check(user.request(method, '/api/v1/tracking/subscriptions', json={}, headers={'Origin':origin,'X-CSRF-Token':user_me['csrf_token']}).status_code == 403, 'tracking_user_write_rejected_'+method)
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
        subscriptions = []
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            subscriptions = user.get('/api/v1/tracking/subscriptions').json().get('data',{}).get('items',[])
            if subscriptions:
                break
            time.sleep(.2)
        check(len(subscriptions) == 1, 'original_Hunter_command_relay_creates_Tracking_subscription')
        subscription = subscriptions[0]
        status = admin.get('/api/v1/commands/' + command)
        check(status.status_code == 200 and status.json()['data']['command_id'] == command and status.json()['data']['subscription_id'] == subscription['subscription_id'], 'strict_gateway_reconciles_original_command')
        check(subscription['observed_state'] != 'running' and subscription['connection'] != 'connected', 'remote_unconfigured_never_claims_running')
        tracking.send_signal(signal.SIGTERM)
        tracking.wait(timeout=12)
        check(web.poll() is None and worker.poll() is None, 'tracking_stop_preserves_website_and_Hunter')
        check(user.get('/api/v1/projects').status_code == 200 and user.get('/api/v1/hunter/signals').status_code == 200, 'website_ready_and_other_domain_survive_tracking_stop')
        check(user.get('/api/v1/tracking/subscriptions').status_code == 503 and user.get('/health/ready').status_code == 200, 'tracking_failure_does_not_fail_website_readiness')
        fixture_code = """
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'services/tracking-worker/python'))
from tracking.store import Store
from tracking.events import normalize
store=Store(Path(sys.argv[1]));row=store.get(sys.argv[2])
tweet=normalize({'id':'17920999990001','text':'本地验收夹具 B3 推文','createdAt':time.time(),'userScreenName':row['handle'],'userIdStr':row['x_user_id'],'isReply':False,'isQuote':False},row['handle'])
assert store.insert_tweet(row,tweet,'wss')
assert not store.insert_tweet(row,tweet,'wss')
print(json.dumps({'inserted':1,'duplicate_rejected':True}))
"""
        seeded = subprocess.run([str(TRACKING_PYTHON), '-c', fixture_code, str(data / 'tracking/tracking.db'), project['project_id']], cwd=ROOT, capture_output=True, text=True)
        check(seeded.returncode == 0, 'offline_normalizer_Store_insert_and_deduplicate_no_parallel_writer')
        tracking = subprocess.Popen([str(NODE), 'services/tracking-worker/dist/main.js'], cwd=ROOT, env=tracking_env, stdout=log, stderr=log, start_new_session=True)
        processes.append(tracking)
        wait_ready(tracking_origin, tracking)
        check(web.poll() is None and worker.poll() is None, 'tracking_restart_independent')
        current_project = admin.get('/api/v1/projects/' + project['project_id']).json()['data']
        rated = admin.patch('/api/v1/projects/' + project['project_id'], json={'rating':'A'}, headers={'Origin':origin, 'X-CSRF-Token':admin_me['csrf_token'], 'Idempotency-Key':str(uuid.uuid4()), 'If-Match':'"rev-'+str(current_project['revision'])+'"'})
        check(rated.status_code == 200, 'authoritative_Projects_rating_for_feed')
        feed = user.get('/api/v1/tracking/latest?profile=published-v1').json()['data']
        check(feed['matched_total'] == 1 and feed['items'][0]['text'] == '本地验收夹具 B3 推文' and feed['items'][0]['rating'] == 'A', 'published_feed_real_B1_C03_UDS_Tracking_projection')
        import sqlite3
        identities = []
        for domain in ('auth','projects','hunter','tracking'):
            db = data / domain / (domain + '.db'); st = db.stat(); identities.append((st.st_dev,st.st_ino))
            with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
                check(conn.execute('pragma integrity_check').fetchone() == ('ok',) and not conn.execute('pragma foreign_key_check').fetchall(), 'physical_database_integrity_'+domain)
        check(len(set(identities)) == 4, 'four_distinct_database_inodes')
        project = admin.get('/api/v1/projects/' + project['project_id']).json()['data']
        project_headers = {'Origin': origin, 'Content-Type': 'application/json', 'X-CSRF-Token': admin_me['csrf_token'], 'Idempotency-Key': str(uuid.uuid4()),
                           'If-Match': '"rev-' + str(project['revision']) + '"'}
        added = admin.post('/api/v1/projects/' + project['project_id'] + '/home-membership', json={'action': 'add'}, headers=project_headers)
        check(added.status_code == 200, 'homepage_add_is_separate_explicit_action')
        check(len(user.get('/api/v1/projects').json()['data']['items']) == 1, 'homepage_public_project_visible')
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
                    for width in (1440, 390):
                        page.set_viewport_size({'width':width,'height':1000})
                        page.goto(origin + '/tracking')
                        page.get_by_text('本地验收夹具 B3 推文', exact=False).first.wait_for(timeout=15000)
                        check(page.get_by_text('未连接真实来源', exact=False).count()>0, f'tracking_truthful_source_{role}_{width}')
                        check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'), f'tracking_layout_{role}_{width}')
                        if role == 'user':
                            check(page.locator('button:has-text("添加账号"):enabled').count()==0, f'tracking_readonly_controls_{width}')
                        page.screenshot(path=str(OUT / f'tracking-{role}-{width}.png'), full_page=True)
                    context.close()
            finally:
                browser.close()
        canonical_before = admin.get('/api/v1/projects/' + project['project_id']).json()['data']
        sub_before = user.get('/api/v1/tracking/subscriptions').json()['data']['items'][0]
        tracking_removed = admin.delete('/api/v1/tracking/subscriptions/' + sub_before['subscription_id'], headers={
            'Origin': origin, 'Content-Type': 'application/json', 'X-CSRF-Token': admin_me['csrf_token'],
            'Idempotency-Key': str(uuid.uuid4()), 'If-Match': '"rev-' + str(sub_before['revision']) + '"'})
        check(tracking_removed.status_code == 202, 'tracking_remove_accepted_not_remote_completion')
        check(admin.get('/api/v1/projects/' + project['project_id']).json()['data'] == canonical_before,
              'Tracking_remove_preserves_Projects_home_data')
        before = user.get('/api/v1/hunter/discoveries/' + discovery['discovery_id']).json()['data']
        current = admin.get('/api/v1/projects/' + project['project_id']).json()['data']
        project_headers.update({'Idempotency-Key': str(uuid.uuid4()), 'If-Match': '"rev-' + str(current['revision']) + '"'})
        removed = admin.delete('/api/v1/projects/' + project['project_id'], headers=project_headers)
        check(removed.status_code == 200, 'homepage_remove_only')
        after = user.get('/api/v1/hunter/discoveries/' + discovery['discovery_id']).json()['data']
        check(before == after, 'Projects_remove_does_not_change_Hunter_discovery')
        check(user.get('/api/v1/tracking/subscriptions').json()['data']['items'][0]['subscription_id'] == subscription['subscription_id'], 'Projects_delete_preserves_Tracking_subscription')
        started, done = threading.Event(), threading.Event()
        stream_state = {}
        def watch():
            try:
                with httpx.Client(base_url=origin, cookies=user.cookies, trust_env=False, timeout=10) as client:
                    with client.stream('GET', '/api/v1/tracking/events') as response:
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
        check(all(user.get(route).status_code == 401 for route in ('/api/v1/hunter/signals','/api/v1/tracking/subscriptions','/api/v1/projects')), 'disabled_user_all_domain_APIs_revoked')
        check(done.wait(6) and stream_state.get('normal_eof'), 'quiet_module_SSE_revoked_without_new_event')
        check(admin.get('/api/v1/auth/me').status_code == 200, 'admin_unaffected_by_synthetic_user_disable')
        report['state'] = 'PASS_B3_LOCAL_COMBINED_EXTERNAL_OFF'
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
