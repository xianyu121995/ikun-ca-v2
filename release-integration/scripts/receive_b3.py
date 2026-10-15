#!/usr/bin/env python3
"""Receive the exact frozen Tracking delivery and only approved website mappings."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
B3 = 'c4de379a67bd9b154bab87ce81d4645b53102ea0'
DELIVERY = 'f3bc19503ae33e000bdd33c140baa1fe77c9109a'
CONTROL = 'd0af2804ed1ad70d3dd66e930582831bbd6b5e96'
UI = 'd90598f4bc595458ce26c5ee1c2e1618e318abc0'
PREFIX = 'services/tracking-worker/python/integration/website/'
EXCLUDED = PREFIX + 'app/api/v1/commands/[id]/route.ts'


def at(commit, path):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transform(target, body):
    if target == 'apps/website/components/tracking-live.tsx':
        assert body.count(b"new EventSource('/api/v1/events/stream')") == 1
        return body.replace(b"new EventSource('/api/v1/events/stream')", b"new EventSource('/api/v1/tracking/events')")
    if target == 'apps/website/app/api/v1/tracking/[[...path]]/route.ts':
        return body.replace(b"export const GET = trackingRoute;", b"import { projectsAuth } from '../../../../../lib/projects';\nfunction route(request: Request) { projectsAuth(); return trackingRoute(request); }\nexport const GET = route;").replace(b'= trackingRoute;', b'= route;')
    if target == 'apps/website/app/api/v1/tracking/events/route.ts':
        return body.replace(b'export const GET = trackingEventsRoute;', b"import { projectsAuth } from '../../../../../lib/projects';\nexport function GET(request: Request) { projectsAuth(); return trackingEventsRoute(request); }")
    return body


def main():
    freeze = json.loads(at(CONTROL, 'docs/progress/b3-freeze.json'))
    assert freeze['accepted_frozen'] and freeze['source_commit'] == B3 and freeze['delivery_commit'] == DELIVERY
    manifest_bytes = at(DELIVERY, freeze['receiving_manifest'])
    assert sha(manifest_bytes) == freeze['receiving_manifest_sha256']
    manifest = json.loads(manifest_bytes)
    for path, expected in manifest['source_inputs'].items():
        assert sha(at(B3, path)) == expected == sha((ROOT / path).read_bytes()), path
    records = {}
    for path in subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', UI, 'apps/website/features/tracking/'], cwd=ROOT, text=True).splitlines():
        body = at(UI, path)
        assert not (ROOT / path).exists() or (ROOT / path).read_bytes() == body, path
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_bytes(body)
        records[path] = {'source_commit': UI, 'source_path': path, 'source_sha256': sha(body)}
    patch = ROOT / manifest['frozen_UI_patch']['source']
    assert sha(patch.read_bytes()) == manifest['frozen_UI_patch']['sha256']
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=ROOT, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=ROOT, check=True)
    for path, expected in manifest['frozen_UI_patch']['final_sha256'].items():
        assert sha((ROOT / path).read_bytes()) == expected
        records[path]['reviewed_patch_sha256'] = sha(patch.read_bytes())
        records[path]['reviewed_patch_output_sha256'] = expected
    for row in manifest['source_mapping']:
        source, target = row['source'], row['formal_target']
        if not source.startswith(PREFIX) or source == EXCLUDED:
            continue
        body = at(B3, source)
        assert sha(body) == row['sha256']
        (ROOT / target).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / target).write_bytes(transform(target, body))
        records[target] = {'source_commit': B3, 'source_path': source, 'source_sha256': sha(body), 'target_sha256': sha(transform(target, body))}
    out = {'state': 'RECEIVED_PENDING_COMBINED_ACCEPTANCE', 'source_commit': B3, 'delivery_commit': DELIVERY, 'control_commit': CONTROL,
           'manifest_sha256': sha(manifest_bytes), 'files': records, 'excluded_command_candidate': EXCLUDED,
           'preserved_global_stream': 'apps/website/app/api/v1/events/stream/route.ts'}
    (ROOT / 'release-integration/night/b3-receiving.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps({'received': len(records), 'source_hashes_verified': len(manifest['source_inputs']), 'global_stream_and_gateway_preserved': True}))


if __name__ == '__main__':
    main()
