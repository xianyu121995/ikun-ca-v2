#!/usr/bin/env python3
"""Record frozen inputs plus explicit approved website wiring patches, never waive originals."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
from receive_b4 import B4, C03, UI, CONTROL, at, ROOT

WIRING = '8b84ee97a94bae28e98b550b2721991f30088486'
BASE = 'f8ceaa87ecf3b6211b0ad7bc8790a850e5e4de3d'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    receiving = json.loads((ROOT / 'release-integration/night/b4-receiving.json').read_text())
    records = receiving['files']
    inputs = {}
    for commit, prefixes in ((B4, ['services/hunter-worker/', 'schemas/hunter/']), (C03, ['modules/projects/'])):
        paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit, *prefixes], cwd=ROOT, text=True).splitlines()
        for path in paths:
            if path.startswith('services/hunter-worker/ui/'):
                continue
            expected = sha(at(commit, path))
            assert sha((ROOT / path).read_bytes()) == expected, path
            inputs[path] = {'source_commit': commit, 'sha256': expected}
    patches = {}
    candidates = {
        'apps/website/lib/projects.ts': (C03, 'modules/projects/integration/website/lib/projects.ts'),
        'apps/website/components/hunter-controller.tsx': (B4, 'services/hunter-worker/python/integration/website/components/hunter-controller.tsx'),
        'apps/website/app/api/v1/commands/[id]/route.ts': (BASE, 'apps/website/app/api/v1/commands/[id]/route.ts'),
    }
    for path in ('apps/website/app/api/v1/hunter/events/route.ts', 'apps/website/app/api/v1/tracking/events/route.ts',
                 'apps/website/lib/service-gateway/commands.ts', 'apps/website/lib/service-gateway/relay.ts', 'apps/website/instrumentation.ts'):
        candidates[path] = (None, None)
    directory = ROOT / 'release-integration/night/patches'
    directory.mkdir(exist_ok=True)
    for index, (path, (commit, source)) in enumerate(candidates.items()):
        before = at(commit, source) if commit else b''
        after = (ROOT / path).read_bytes()
        patch = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                           fromfile='a/' + path if commit else '/dev/null', tofile='b/' + path)).encode()
        patch_path = directory / ('site-' + str(index + 1) + '.patch')
        patch_path.write_bytes(patch)
        patches[path] = {'baseline_commit': commit, 'baseline_path': source, 'baseline_sha256': sha(before),
                         'patch_path': str(patch_path.relative_to(ROOT)), 'patch_sha256': sha(patch), 'target_sha256': sha(after)}
    for path, row in records.items():
        expected = patches[path]['target_sha256'] if path in patches else row.get('reviewed_patch_output_sha256', row['source_sha256'])
        assert sha((ROOT / path).read_bytes()) == expected, path
    result = {'source_commit': B4, 'control_commit': CONTROL, 'wiring_control_commit': WIRING,
              'projects_commit': C03, 'ui_commit': UI, 'frozen_domain_inputs': inputs,
              'received_website_inputs': records, 'site_patches': patches,
              'original_immutable_and_homepage_checks_remain_required': True}
    (ROOT / 'release-integration/night/source-binding.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'frozen_domain_paths': len(inputs), 'website_inputs': len(records), 'site_patches': len(patches)}))


if __name__ == '__main__':
    main()
