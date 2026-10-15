#!/usr/bin/env python3
"""Receive only frozen B4 website mappings and the exact reviewed Hunter UI patch."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
B4 = '10fe9d73dcf9d2dd296b808e8aaee41308f12112'
CONTROL = '7a90ec281211cc8a307692c8e420cf4b802ce452'
C03 = 'aa51a640a159e4c8f6cdd841a25f4279e73075ba'
UI = '08065d700239b20fb4c887bbd0c85321904687f8'


def at(commit, path):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    freeze = json.loads(at(CONTROL, 'docs/progress/b4-freeze.json'))
    manifest_raw = at(B4, freeze['receiving_manifest'])
    assert digest(manifest_raw) == freeze['receiving_manifest_sha256']
    manifest = json.loads(manifest_raw)
    records = {}
    for item in manifest['files']:
        if item['kind'] != 'website_candidate':
            continue
        content = at(B4, item['source'])
        assert digest(content) == item['sha256']
        destination = ROOT / item['target']
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        records[item['target']] = {'source_commit': B4, 'source_path': item['source'],
                                   'source_sha256': item['sha256']}
    helper = 'modules/projects/integration/website/lib/projects.ts'
    content = at(C03, helper)
    assert digest(content) == '013ca12ed02a8e0c476b6e20563282f583b30497c366590378b8dafebf98616c'
    (ROOT / 'apps/website/lib/projects.ts').write_bytes(content)
    records['apps/website/lib/projects.ts'] = {'source_commit': C03, 'source_path': helper,
                                              'source_sha256': digest(content)}
    prefix = 'apps/website/features/hunter-discovery/'
    ui_files = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', UI, prefix], cwd=ROOT, text=True).splitlines()
    assert ui_files
    for path in ui_files:
        content = at(UI, path)
        destination = ROOT / path
        assert not destination.exists() or destination.read_bytes() == content, path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        records[path] = {'source_commit': UI, 'source_path': path, 'source_sha256': digest(content)}
    patch = ROOT / 'services/hunter-worker/python/integration/patches/hunter-live.patch'
    assert digest(patch.read_bytes()) == freeze['ui_patch_sha256']
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=ROOT, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=ROOT, check=True)
    for path, expected in freeze['patched_ui_output_sha256'].items():
        assert digest((ROOT / path).read_bytes()) == expected, path
        records[path]['reviewed_patch_sha256'] = freeze['ui_patch_sha256']
        records[path]['reviewed_patch_output_sha256'] = expected
    output = ROOT / 'release-integration/night/b4-receiving.json'
    output.write_text(json.dumps({'state': 'RECEIVED_PENDING_SITE_WIRING_AND_TESTS',
                                  'source_commit': B4, 'control_commit': CONTROL,
                                  'ui_commit': UI, 'projects_commit': C03, 'files': records}, indent=2) + '\n')
    print(json.dumps({'status': 'RECEIVED_FROZEN_WEBSITE_CANDIDATES', 'mapped_files': len(records),
                      'reviewed_ui_patch_files': 2, 'worker_deployed': False}))


if __name__ == '__main__':
    main()
