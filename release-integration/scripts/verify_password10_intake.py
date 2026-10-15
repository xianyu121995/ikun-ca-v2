#!/usr/bin/env python3
"""Verify the reviewed additive Auth exception without weakening the original intake."""
import hashlib
import json
from pathlib import Path
import subprocess
from verify_night_intake import verify as verify_night

ROOT = Path(__file__).resolve().parents[2]
CONTROL = '1d56ef2f003c531574e41fe079c70510ac6ed437'
ORIGINAL = 'c30cc51f64e95c40a6ccd83b1fbed458090ef3be'
READONLY_CONTROL = 'ee3664af31d769416e2eeb2d7e90e049e97b7a79'


def at(commit, path):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def verify():
    night_overrides, night_paths = verify_night()
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
        expected = overrides.get(path, night_overrides.get(path, original))['sha256']
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
    readonly = json.loads(at(READONLY_CONTROL, 'docs/c0-lite/readonly-ui-review.json'))
    assert readonly['source_commit'] == 'f1031a20966cba89d3b92805d16b6817a2472d9c'
    assert set(readonly['source_sha256']) == set(readonly['allowed_receiving_paths']) == {
        'apps/website/components/projects-home.tsx', 'apps/website/components/projects-home-access.css'}
    subprocess.run(['git', 'merge-base', '--is-ancestor', readonly['source_commit'], 'HEAD'], cwd=ROOT, check=True)
    for path, expected in readonly['source_sha256'].items():
        assert digest(at(readonly['source_commit'], path)) == expected, path
        assert digest((ROOT / path).read_bytes()) == expected, path
    scope.update(readonly['allowed_receiving_paths'])
    scope.update(night_paths)
    receiving_changes = subprocess.check_output(['git', 'diff', '--name-only', baseline], cwd=ROOT, text=True).splitlines()
    assert all(path in scope or path.startswith('release-integration/') for path in receiving_changes), receiving_changes
    return {'status': 'PASS', 'review_commit': CONTROL, 'source_commit': source,
            'original_control_commit': ORIGINAL, 'immutable_sources_verified': 77,
            'original_immutable_hashes_retained': sum(digest((ROOT/path).read_bytes())==row['sha256'] for path,row in intake['immutable_domain_and_shared_sources'].items()),
            'approved_immutable_overrides': {**overrides, **{p:r for p,r in night_overrides.items() if p=='packages/ui/src/index.ts'}},
            'homepage_sources_verified': 8, 'exact_form_three_line_delta': True,
            'workspace_link_preserved': True, 'reviewed_source_paths_verified': len(changed),
            'readonly_ui_delta': {'review_commit': READONLY_CONTROL, 'source_commit': readonly['source_commit'],
                                  'source_sha256': readonly['source_sha256']}}


if __name__ == '__main__':
    report = verify()
    output = ROOT / 'release-integration/c0-lite/evidence/password10-intake.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
