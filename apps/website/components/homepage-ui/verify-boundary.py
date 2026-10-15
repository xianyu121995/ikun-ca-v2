#!/usr/bin/env python3
"""Read-only code boundary audit, plus local evidence generation. No DB/API reads."""
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

module = Path(__file__).resolve().parent
root = module.parents[3]
baseline = 'f89d8f55fc3e68d6360e7a1e33e23bde48591098'
names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', baseline], cwd=root, text=True).splitlines()
for name in names:
    expected = subprocess.check_output(['git', 'show', baseline + ':' + name], cwd=root)
    assert (root / name).read_bytes() == expected, 'Protected baseline changed: ' + name
sources = list(module.glob('*.tsx')) + list((module / 'model').glob('*.ts'))
route = root / 'apps/website/app/prototypes/homepage/page.tsx'
sources.append(route)
for source in sources:
    text = source.read_text()
    assert not re.search(r'\b(fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(', text), source
    assert 'shared-snapshot' not in text and 'lucide-react' not in text, source
stats = json.loads((module / 'evidence/test-results.json').read_text())['stats']
assert stats['expected'] == 10 and stats['unexpected'] == 0 and stats['skipped'] == 0
gates = json.loads((module / 'evidence/preview-gates.json').read_text())
assert gates['production_with_flag'] == 404 and gates['disabled_flag'] == 404
proof = {
    'verified_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
    'baseline': baseline,
    'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip(),
    'protected_baseline_files_unchanged': len(names),
    'scope': 'homepage UI candidate; prototype route and module only',
    'source_hashes': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)},
    'application_network_clients': 0,
    'business_database_created': any((root / 'var').rglob('*.db')),
    'runtime_dependency_changes': False,
    'root_dependency_or_contract_changes': False,
    'dependency_install': 'pnpm install --frozen-lockfile in independent Worktree',
    'qa_tool': '@playwright/test 1.64.0 installed only in ignored module .tools',
    'build': 'website Next 16.4.1 build passed; cpus=1; separate shared build passed',
    'typecheck': 'pnpm --filter @ikun/website typecheck passed',
    'browser_acceptance': {'passed': stats['expected'], 'failed': stats['unexpected'], 'duration_ms': stats['duration']},
    'preview_gates': gates,
    'integration_status': ['PENDING_SHARED_UI', 'PENDING_PROJECTS_OWNER'],
    'not_verified': ['real auth', 'real project API', 'database persistence', 'collectors or Watch', 'deployment'],
}
assert not proof['business_database_created'], 'UI-only QA must not create business databases.'
(module / 'evidence/verification.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'baseline_files_unchanged': len(names), 'browser_passed': stats['expected'], 'preview_gates': gates}, ensure_ascii=False))
