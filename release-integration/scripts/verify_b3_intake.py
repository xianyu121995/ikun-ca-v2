#!/usr/bin/env python3
"""Add exact B3 freeze verification without weakening B4/C03/original intake."""
import json
import difflib
import subprocess
from receive_b3 import ROOT, B3, DELIVERY, CONTROL, UI, PREFIX, EXCLUDED, at, sha, transform


def verify():
    freeze = json.loads(at(CONTROL, 'docs/progress/b3-freeze.json'))
    body = at(DELIVERY, freeze['receiving_manifest'])
    assert sha(body) == freeze['receiving_manifest_sha256']
    manifest = json.loads(body)
    receipt = json.loads((ROOT / 'release-integration/night/b3-receiving.json').read_text())
    assert receipt['source_commit'] == B3 and receipt['delivery_commit'] == DELIVERY and receipt['control_commit'] == CONTROL
    assert receipt['manifest_sha256'] == sha(body)
    subprocess.run(['git', 'merge-base', '--is-ancestor', DELIVERY, 'HEAD'], cwd=ROOT, check=True)
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', DELIVERY, 'services/tracking-worker/', 'schemas/tracking/'], cwd=ROOT, text=True).splitlines()
    allowed = set(paths)
    for path in paths:
        assert (ROOT / path).read_bytes() == at(DELIVERY, path), path
    for path, expected in manifest['source_inputs'].items():
        assert sha(at(B3, path)) == expected == sha((ROOT / path).read_bytes()), path
    mappings = {row['formal_target']: row for row in manifest['source_mapping'] if row['source'].startswith(PREFIX) and row['source'] != EXCLUDED}
    ui_paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', UI, 'apps/website/features/tracking/'], cwd=ROOT, text=True).splitlines()
    assert set(receipt['files']) == set(mappings) | set(ui_paths)
    for path, row in receipt['files'].items():
        if path in mappings:
            source = mappings[path]['source']
            assert row['source_commit'] == B3 and row['source_path'] == source
            before = at(B3, source)
            assert row['source_sha256'] == sha(before)
            expected = transform(path, before)
            assert row['target_sha256'] == sha(expected)
        else:
            assert row['source_commit'] == UI and row['source_path'] == path
            expected = at(UI, path)
            assert row['source_sha256'] == sha(expected)
            patched = manifest['frozen_UI_patch']['final_sha256'].get(path)
            if patched:
                assert sha((ROOT / path).read_bytes()) == patched
                assert row['reviewed_patch_output_sha256'] == patched
                expected = (ROOT / path).read_bytes()
        assert (ROOT / path).read_bytes() == expected, path
        allowed.add(path)
    # These are intentionally NOT replaced with the owner's preview implementations.
    for path in ('apps/website/app/api/v1/events/stream/route.ts', 'apps/website/app/api/v1/commands/[id]/route.ts',
                 'apps/website/lib/service-gateway/commands.ts', 'apps/website/lib/service-gateway/relay.ts'):
        assert (ROOT / path).read_bytes() == at('25dcb4ef066a135694ee88e7744c01a78919693c', path), path
    binding = ROOT / 'release-integration/night/b3-source-binding.json'
    if binding.exists():
        bound = json.loads(binding.read_text())
        assert bound['source_commit'] == B3 and bound['control_commit'] == CONTROL
        assert bound['received_files'] == receipt['files']
        expected_paths = {p for p,r in receipt['files'].items() if r.get('target_sha256',r['source_sha256']) != r['source_sha256']}
        assert set(bound['site_patches']) == expected_paths
        for target,row in bound['site_patches'].items():
            before,after = at(B3,row['source_path']), (ROOT/target).read_bytes()
            patch = ''.join(difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),n=0,fromfile='a/'+target,tofile='b/'+target)).encode()
            assert patch == (ROOT/row['patch_path']).read_bytes()
            assert sha(patch) == row['patch_sha256'] and sha(before) == row['source_sha256'] and sha(after) == row['target_sha256']
    overrides = {path: {'sha256': sha(at(B3, path)), 'source_commit': B3, 'control_commit': CONTROL}
                 for path in manifest['source_inputs'] if path.startswith(('services/tracking-worker/', 'schemas/tracking/'))}
    return overrides, allowed
