#!/usr/bin/env python3
"""Validate only approved B4/C03 exceptions to the unchanged original C0 intake."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
B4 = '10fe9d73dcf9d2dd296b808e8aaee41308f12112'
C03 = 'aa51a640a159e4c8f6cdd841a25f4279e73075ba'
CONTROL = '7a90ec281211cc8a307692c8e420cf4b802ce452'
WIRING = '8b84ee97a94bae28e98b550b2721991f30088486'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def at(commit, path):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


def verify():
    path = ROOT / 'release-integration/night/source-binding.json'
    if not path.exists():
        return {}, set()
    record = json.loads(path.read_text())
    assert record['source_commit'] == B4 and record['projects_commit'] == C03
    assert record['control_commit'] == CONTROL and record['wiring_control_commit'] == WIRING
    freeze = json.loads(at(CONTROL, 'docs/progress/b4-freeze.json'))
    assert freeze['source_commit'] == B4 and freeze['required_wiring_control'] == WIRING
    assert 'v2-site-gateway-v1' in at(WIRING, 'docs/progress/SITE-GATEWAY-ADDENDUM.md').decode()
    for commit in (B4, C03):
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=ROOT, check=True)
    allowed = set()
    overrides = {}
    for source, row in record['frozen_domain_inputs'].items():
        commit = row['source_commit']
        assert commit in (B4, C03)
        prefixes = ('services/hunter-worker/', 'schemas/hunter/') if commit == B4 else ('modules/projects/',)
        assert source.startswith(prefixes) and not source.startswith('services/hunter-worker/ui/')
        assert digest(at(commit, source)) == row['sha256'] == digest((ROOT / source).read_bytes()), source
        allowed.add(source)
        if source.startswith('modules/projects/candidate/projects_service/'):
            overrides[source] = {'sha256': row['sha256'], 'source_commit': C03, 'control_commit': CONTROL}
    patches = record['site_patches']
    permitted = {'apps/website/lib/projects.ts', 'apps/website/components/hunter-controller.tsx',
                 'apps/website/app/api/v1/commands/[id]/route.ts', 'apps/website/app/api/v1/hunter/events/route.ts',
                 'apps/website/app/api/v1/tracking/events/route.ts', 'apps/website/instrumentation.ts',
                 'apps/website/lib/service-gateway/commands.ts', 'apps/website/lib/service-gateway/relay.ts',
                 'apps/website/features/hunter-discovery/v3/App.tsx'}
    assert set(patches) == permitted
    for target, row in patches.items():
        assert digest((ROOT / row['patch_path']).read_bytes()) == row['patch_sha256']
        assert digest((ROOT / target).read_bytes()) == row['target_sha256'], target
        original = at(row['baseline_commit'], row['baseline_path']) if row['baseline_commit'] else b''
        assert digest(original) == row['baseline_sha256']
        allowed.add(target)
    helper = at(C03, 'modules/projects/integration/website/lib/projects.ts')
    expected = helper.replace(b"const globalState=", b"readPaths.push(/^\\/api\\/v1\\/hunter\\/events$/, /^\\/api\\/v1\\/tracking\\/events$/);\nconst globalState=", 1)
    assert (ROOT / 'apps/website/lib/projects.ts').read_bytes() == expected, 'only two exact readPaths allowed'
    for target, row in record['received_website_inputs'].items():
        assert digest(at(row['source_commit'], row['source_path'])) == row['source_sha256']
        expected_hash = patches[target]['target_sha256'] if target in patches else row.get('reviewed_patch_output_sha256', row['source_sha256'])
        assert digest((ROOT / target).read_bytes()) == expected_hash, target
        allowed.add(target)
    # User explicitly required the existing tracking navigation wording before deployment.
    # Reuse the already received WorkspaceLink; reverse only these two receiving lines.
    app = (ROOT / 'apps/website/features/hunter-discovery/v3/App.tsx').read_bytes()
    before_caption = app.replace(b"import {WorkspaceLink} from '../../../components/auth/forms';\n", b'', 1).replace(b'LinkComponent={live?WorkspaceLink:Link}', b'LinkComponent={Link}', 1)
    assert digest(before_caption) == freeze['patched_ui_output_sha256']['apps/website/features/hunter-discovery/v3/App.tsx']
    return overrides, allowed
