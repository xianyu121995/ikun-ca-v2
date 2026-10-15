#!/usr/bin/env python3
"""Record source and exact three receiving patches for the Tracking aliases."""
import difflib
import json
from receive_b3 import ROOT, B3, CONTROL, DELIVERY, at, sha
from verify_b3_intake import verify


def main():
    verify()
    receipt = json.loads((ROOT / 'release-integration/night/b3-receiving.json').read_text())
    patches = {}
    for path, row in receipt['files'].items():
        if 'target_sha256' not in row or row['target_sha256'] == row['source_sha256']:
            continue
        before, after = at(B3, row['source_path']), (ROOT / path).read_bytes()
        body = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True), n=0, fromfile='a/'+path, tofile='b/'+path)).encode()
        patch_path = 'release-integration/night/patches/b3-' + str(len(patches)+1) + '.patch'
        (ROOT / patch_path).write_bytes(body)
        patches[path] = {'source_commit': B3, 'source_path': row['source_path'], 'source_sha256': sha(before),
                         'patch_path': patch_path, 'patch_sha256': sha(body), 'target_sha256': sha(after)}
    record = {'source_commit': B3, 'delivery_commit': DELIVERY, 'control_commit': CONTROL, 'site_patches': patches,
              'source_manifest_sha256': receipt['manifest_sha256'], 'received_files': receipt['files'],
              'original_77_and_homepage_8_and_B4_C03_verification_required': True}
    (ROOT / 'release-integration/night/b3-source-binding.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'B3_receiving_files':len(receipt['files']), 'exact_patches':len(patches)}))


if __name__ == '__main__': main()
