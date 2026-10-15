#!/usr/bin/env python3
"""Read-only evidence for the owned B3 website/Tracking and preserved B4 Hunter, using safe fields only."""
from contextlib import closing
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import urllib.request
from deploy_c0_lite import ROOT, TARGET, digest
from night_worker_ops import inside, private_json


def main():
    report = json.loads((ROOT / 'release-integration/.runtime/night-b3/deployment.json').read_text())
    candidate = report['candidate_sha']
    owner = private_json(TARGET / 'owner.json')
    env = private_json(TARGET / 'config/web.environment.json')
    hunter = private_json(TARGET / 'config/hunter.environment.json')
    tracking = private_json(TARGET / 'config/tracking.environment.json')
    assert env['TRACKING_API_TOKEN'] == tracking['TRACKING_API_TOKEN'] and tracking['TRACKING_API_TOKEN'] not in (hunter['HUNTER_API_TOKEN'],hunter['PROJECTS_INGEST_HUNTER_TOKEN'])
    assert env['TRACKING_API_URL'] == 'http://127.0.0.1:4012' and tracking['IKUN_TRACKING_EXTERNAL_IO_DISABLED'] == '1'
    assert owner['candidate_sha'] == env['IKUN_RELEASE_SHA'] == candidate
    assert env['DATA_ROOT'] == hunter['DATA_ROOT'] == str(TARGET / 'data')
    assert env['IKUN_AUTH_ORIGIN'] == 'https://v2.ikun.ca' and 'IKUN_AUTH_DEV' not in env
    assert env['HUNTER_API_TOKEN'] == hunter['HUNTER_API_TOKEN']
    assert env['PROJECTS_INGEST_HUNTER_TOKEN'] == hunter['PROJECTS_INGEST_HUNTER_TOKEN']
    assert env['HUNTER_API_TOKEN'] != env['PROJECTS_INGEST_HUNTER_TOKEN']
    assert hunter['HUNTER_EXTERNAL_IO_ENABLED'] == '0'
    release = TARGET / 'releases' / candidate
    binding = json.loads((release / 'release-integration/c0-lite/evidence/build-binding.json').read_text())
    for path, expected in {**binding['sources'], **binding['compiled']}.items():
        assert digest(release / path) == expected, path
    jobs = {}
    for name in ('web', 'hunter', 'tracking', 'tunnel'):
        label = 'ca.ikun.v2.c0lite.' + name
        result = subprocess.run(['/bin/launchctl', 'print', 'gui/' + str(os.getuid()) + '/' + label], capture_output=True, text=True)
        match = re.search(r'^\s*pid = (\d+)$', result.stdout, re.M)
        jobs[name] = {'label': label, 'loaded': result.returncode == 0, 'pid': int(match[1]) if match else None}
    assert jobs['web']['pid'] and jobs['hunter']['pid'] and jobs['web']['pid'] != jobs['hunter']['pid']
    assert jobs['tracking']['pid'] and len({jobs[x]['pid'] for x in ('web','hunter','tracking')}) == 3
    from night_worker_ops import validate
    plan = private_json(Path(report['runtime_plan']))
    validate(plan)
    hunter_plan = private_json(TARGET/'plans/hunter/75b81a2b5210e41bdf8522467c7fba2a6a6e693c/worker.json')
    assert hunter_plan['candidate_sha'] == '75b81a2b5210e41bdf8522467c7fba2a6a6e693c' and hunter_plan['source_commit'] == '10fe9d73dcf9d2dd296b808e8aaee41308f12112'
    stores, identities = {}, set()
    for domain in ('auth', 'projects', 'hunter', 'tracking'):
        path = inside(TARGET / 'data' / domain / (domain + '.db'), TARGET / 'data')
        info = path.stat()
        assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
        identity = (info.st_dev, info.st_ino)
        assert identity not in identities
        identities.add(identity)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            stores[domain] = {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino,
                              'mode': '0600', 'links': 1, 'integrity': 'ok',
                              'application_id': db.execute('PRAGMA application_id').fetchone()[0],
                              'user_version': db.execute('PRAGMA user_version').fetchone()[0]}
    assert stores['hunter']['user_version'] == 4 and stores['hunter']['application_id'] == 0x494B0201
    assert stores['tracking']['user_version'] == 4 and stores['tracking']['application_id'] == 1229652482
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    health = {}
    for name, port in (('web', 4000), ('hunter', 4011), ('tracking', 4012)):
        with opener.open('http://127.0.0.1:' + str(port) + '/health/ready', timeout=3) as response:
            assert response.status == 200
            health[name] = json.load(response)['data']
    assert health['hunter']['external_io_enabled'] is False and health['tracking']['external_collection_enabled'] is False
    assert health['web']['workers_enabled'] and all(health['web']['workers'][x]['configured'] for x in ('hunter','tracking'))
    code = "const{pathToFileURL}=await import('node:url');const root=process.argv[1];const{LocalAccounts}=await import(pathToFileURL(root+'/modules/auth/dist/src/local.js'));const{environment}=await import(pathToFileURL(root+'/modules/auth/dist/src/config.js'));const a=new LocalAccounts(environment());try{const users=a.list();const t=users.find(x=>x.username==='c0_pub_viewer_1792079586');const s=users.find(x=>x.username==='admin');if(!t||t.enabled||!s?.enabled)throw Error('FIXTURE_OR_ADMIN_STATE');console.log(JSON.stringify({temporary_enabled:false,temporary_role:t.role,admin_enabled:true,admin_role:s.role}));}finally{a.close();}"
    result = subprocess.run([str(TARGET / 'toolchains/node24/bin/node'), '--input-type=module', '-e', code, str(release)], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, 'AUTH_OWNER_FIXTURE_STATE_CHECK'
    accounts = json.loads(result.stdout)
    logs = {}
    for name in ('web.log', 'web.error.log', 'hunter.log', 'hunter.error.log', 'tracking.log', 'tracking.error.log'):
        path = TARGET / 'logs' / name
        info = path.stat()
        assert stat.S_IMODE(info.st_mode) == 0o600 and not path.is_symlink()
        content = path.read_bytes()
        assert not any(value.encode() in content for value in (hunter['HUNTER_API_TOKEN'], hunter['PROJECTS_INGEST_HUNTER_TOKEN'], tracking['TRACKING_API_TOKEN']))
        logs[name] = {'bytes': info.st_size, 'mode': '0600', 'direction_credentials_present': False}
    process_table = subprocess.check_output(['/bin/ps', '-axo', 'pid=,ppid=,rss=,comm='], text=True).splitlines()
    rows = [line.strip().split(None, 3) for line in process_table]
    selected = {job['pid'] for job in jobs.values() if job['pid']}
    while True:
        old = len(selected)
        selected.update(int(row[0]) for row in rows if len(row) == 4 and int(row[1]) in selected)
        if len(selected) == old:
            break
    processes = [{'pid': int(row[0]), 'ppid': int(row[1]), 'rss_kib': int(row[2]), 'executable': row[3]}
                 for row in rows if len(row) == 4 and int(row[0]) in selected]
    output = {'state': 'PASS_OWNED_RUNTIME_READONLY_AUDIT', 'running_commit': candidate,
              'build_id': binding['build_id'], 'source_hashes_verified': len(binding['sources']),
              'compiled_hashes_verified': len(binding['compiled']), 'jobs': jobs, 'databases': stores,
              'health': health, 'accounts': accounts, 'logs': logs, 'processes': processes,
              'owned_rss_mib': round(sum(row['rss_kib'] for row in processes) / 1024, 1),
              'worker_metadata_is_configuration_only': True, 'worker_failures_do_not_gate_website_ready': True,
              'hunter_release_preserved': hunter_plan['candidate_sha'], 'Tracking_source': plan['source_commit']}
    file = ROOT / 'release-integration/.runtime/night-b3/final-runtime-audit.json'
    file.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n')
    file.chmod(0o600)
    print(json.dumps({'state': output['state'], 'running_commit': candidate, 'source_hashes': len(binding['sources']),
                      'compiled_hashes': len(binding['compiled']), 'temporary_enabled': False,
                      'rss_mib': output['owned_rss_mib']}))


if __name__ == '__main__':
    main()
