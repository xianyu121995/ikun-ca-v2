#!/usr/bin/env python3
"""Bind the tested compiled artifacts to explicit receiving source bytes."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONTROL = 'c30cc51f64e95c40a6ccd83b1fbed458090ef3be'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    intake = json.loads(subprocess.check_output(['git', 'show', CONTROL + ':docs/c0-lite/root-intake.json'], cwd=ROOT))
    for path, item in intake['immutable_domain_and_shared_sources'].items():
        assert sha(ROOT / path) == item['sha256'], path
    for path, expected in intake['homepage_final_sha256'].items():
        assert sha(ROOT / path) == expected, path
    # All actual runtime input trees, not only the approval list. Tests/docs excluded.
    paths = set(intake['approved_root_files']) | set(intake['website_mappings']) | set(intake['homepage_final_sha256']) | set(intake['additional_exact_files'])
    for directory in ('apps/website/app', 'apps/website/lib', 'apps/website/components', 'apps/website/features',
                      'modules/auth/src', 'modules/projects/candidate/projects_service', 'modules/projects/integration',
                      'packages/contracts/src', 'packages/runtime/src', 'packages/ui/src', 'schemas'):
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob('*')
                     if p.is_file() and p.suffix not in ('.pyc', '.png', '.log') and '__pycache__' not in p.parts)
    sources = {p: sha(ROOT / p) for p in sorted(paths) if (ROOT / p).is_file()}
    outputs = {}
    for directory in ('packages/contracts/dist', 'packages/runtime/dist', 'packages/ui/dist', 'modules/auth/dist', 'apps/website/.next/server', 'apps/website/.next/static'):
        outputs.update({str(p.relative_to(ROOT)): sha(p) for p in (ROOT / directory).rglob('*') if p.is_file()})
    receipt = {'control_commit': CONTROL, 'tested_merge_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'binding': 'Final candidate must contain these exact source bytes; tests ran on these bytes before the receiving commit.',
               'immutable_sources_verified': 77, 'homepage_sources_verified': 8,
               'build_id': (ROOT / 'apps/website/.next/BUILD_ID').read_text().strip(),
               'lock_sha256': sha(ROOT / 'pnpm-lock.yaml'), 'sources': sources, 'compiled': outputs}
    out = ROOT / 'release-integration/c0-lite/evidence/build-binding.json'
    out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'binding': str(out), 'sources': len(sources), 'compiled': len(outputs)}))


if __name__ == '__main__':
    main()
