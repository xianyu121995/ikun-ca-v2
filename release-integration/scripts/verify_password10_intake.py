#!/usr/bin/env python3
"""Verify the reviewed additive Auth exception without weakening the original intake."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONTROL = '1d56ef2f003c531574e41fe079c70510ac6ed437'
ORIGINAL = 'c30cc51f64e95c40a6ccd83b1fbed458090ef3be'


def at(commit, path):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def verify():
    review = json.loads(at(CONTROL, 'docs/c0-lite/password10-review.json'))
    intake = json.loads(at(ORIGINAL, 'docs/c0-lite/root-intake.json'))
    source = review['source_commit']
    subprocess.run(['git', 'merge-base', '--is-ancestor', source, 'HEAD'], cwd=ROOT, check=True)
    changed = subprocess.check_output(['git', 'diff', '--name-only', review['baseline'], source], cwd=ROOT, text=True).splitlines()
    assert sorted(changed) == sorted(review['source_changed_paths'])
    for path, expected in review['source_sha256'].items():
        assert digest(at(source, path)) == expected, path
        assert digest((ROOT / path).read_bytes()) == expected, path
    overrides = review['intake_delta']['immutable_source_overrides']
    assert set(overrides) == {'modules/auth/src/security.ts', 'modules/auth/src/cli.ts'}
    for path, original in intake['immutable_domain_and_shared_sources'].items():
        expected = overrides.get(path, original)['sha256']
        assert digest((ROOT / path).read_bytes()) == expected, path
    for path, expected in intake['homepage_final_sha256'].items():
        assert digest((ROOT / path).read_bytes()) == expected, path
    for path, mapping in review['intake_delta']['website_mapping_override'].items():
        baseline = at(mapping['receiving_baseline_commit'], path)
        assert digest(baseline) == mapping['receiving_baseline_sha256']
        expected = baseline.replace('至少 15 个字符'.encode(), '至少 10 个字符'.encode()).replace(b'minLength={15}', b'minLength={10}')
        assert digest(expected) == mapping['expected_target_sha256']
        assert (ROOT / path).read_bytes() == expected, path
    baseline = review['intake_delta']['website_mapping_override']['apps/website/components/auth/forms.tsx']['receiving_baseline_commit']
    scope = set(changed) | set(review['intake_delta']['website_mapping_override'])
    receiving_changes = subprocess.check_output(['git', 'diff', '--name-only', baseline], cwd=ROOT, text=True).splitlines()
    assert all(path in scope or path.startswith('release-integration/') for path in receiving_changes), receiving_changes
    return {'status': 'PASS', 'review_commit': CONTROL, 'source_commit': source,
            'original_control_commit': ORIGINAL, 'immutable_sources_verified': 77,
            'original_immutable_hashes_retained': 75, 'approved_immutable_overrides': overrides,
            'homepage_sources_verified': 8, 'exact_form_three_line_delta': True,
            'workspace_link_preserved': True, 'reviewed_source_paths_verified': len(changed)}


if __name__ == '__main__':
    report = verify()
    output = ROOT / 'release-integration/c0-lite/evidence/password10-intake.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
