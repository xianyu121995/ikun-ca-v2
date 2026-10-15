#!/usr/bin/env python3
"""Receive only the exact C0-lite approved website mappings from pinned Git objects."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONTROL = 'c30cc51f64e95c40a6ccd83b1fbed458090ef3be'


def at(sha, path):
    return subprocess.check_output(['git', 'show', f'{sha}:{path}'], cwd=ROOT)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    manifest = json.loads(at(CONTROL, 'docs/c0-lite/root-intake.json'))
    approved = json.loads(at(CONTROL, 'docs/c0-lite/release.json'))
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() == 'codex/integration'
    record = {'control_commit': CONTROL, 'source_commits': approved['source_commits'], 'mappings': {}, 'immutable_files': {}}
    for name, item in manifest['immutable_domain_and_shared_sources'].items():
        actual = sha((ROOT / name).read_bytes())
        assert actual == item['sha256'], f'Immutable source mismatch: {name}'
        record['immutable_files'][name] = actual
    for name, item in manifest['website_mappings'].items():
        data = at(item['source_commit'], item['source_path'])
        assert sha(data) == item['source_sha256'], f'Mapping source mismatch: {name}'
        target = ROOT / name
        record['mappings'][name] = {**item, 'previous_sha256': sha(target.read_bytes()) if target.exists() else None}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    patch = manifest['homepage_patch']
    data = at(patch['source_commit'], patch['source_path'])
    assert sha(data) == patch['sha256']
    subprocess.run(['git', 'apply', '--unidiff-zero', '--check', '-'], input=data, cwd=ROOT, check=True)
    subprocess.run(['git', 'apply', '--unidiff-zero', '-'], input=data, cwd=ROOT, check=True)
    for name, expected in manifest['homepage_final_sha256'].items():
        assert sha((ROOT / name).read_bytes()) == expected, f'Homepage result mismatch: {name}'
    record['homepage_final_sha256'] = manifest['homepage_final_sha256']
    record['homepage_patch_sha256'] = patch['sha256']
    record['main_frozen_at'] = approved['main_frozen_at']
    out = ROOT / 'release-integration/c0-lite/evidence/receiving.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(f'Received {len(record["mappings"])} mappings; {len(record["immutable_files"])} immutable sources unchanged; reviewed homepage hashes match')


if __name__ == '__main__':
    main()
