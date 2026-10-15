"""One foreground final-source process/browser batch. Caller owns the shared heavy lock."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone

MODULE=Path(__file__).resolve().parents[1]
ROOT=MODULE.parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def sources():
    files=list((MODULE/'hunterradar').glob('*.py'))+list((ROOT/'schemas/hunter').glob('*.sql'))+list((MODULE/'integration/website').rglob('*'))+list((MODULE/'scripts').glob('*b4.py'))
    files += [ROOT/'services/hunter-worker/src/main.ts',MODULE/'integration/patches/hunter-live.patch']
    files += [p for p in (MODULE/'integration/tests').rglob('*') if p.is_file() and p.suffix in ('.mjs','.cjs','.tsx','.py')]
    files += list((MODULE/'tests').glob('*.py'))+list((MODULE/'tests').glob('*.cjs'))
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(set(files)) if p.is_file()}
before=sources();started=datetime.now(timezone.utc).isoformat()
build=json.loads((MODULE/'var/b4/evidence/build.json').read_text())
for relative,checksum in build['candidate_files_sha256'].items():
    if sha(MODULE/relative)!=checksum:raise RuntimeError('candidate_changed_after_build:'+relative)
if sha(MODULE/'integration/patches/hunter-live.patch')!=build['ui_patch_sha256']:raise RuntimeError('ui_patch_changed_after_build')
for command in [['pnpm','--filter','@ikun/hunter-worker','build'],[sys.executable,'scripts/process_smoke_b4.py'],[sys.executable,'scripts/restore_kill_b4.py'],[sys.executable,'scripts/browser_batch_b4.py','formal'],[sys.executable,'scripts/browser_batch_b4.py','legacy']]:
    subprocess.run(command,cwd=MODULE if command[0]==sys.executable else ROOT,env=os.environ.copy(),check=True)
if before!=sources():raise RuntimeError('source_changed_during_final_batch')
output={'status':'passed','started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_files_sha256':before,'same_source_entire_batch':True,'provider_calls':0,
        'process':json.loads((MODULE/'docs/b4/process-smoke-night.json').read_text()),
        'restore_kill':json.loads((MODULE/'docs/b4/restore-kill.json').read_text()),
        'formal_browser':json.loads((MODULE/'docs/b4/browser/results.json').read_text()),
        'legacy_browser':json.loads((MODULE/'docs/b4/legacy-browser/results.json').read_text())}
(MODULE/'docs/b4/final-batch.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
print('B4_FINAL_SAME_SOURCE_BATCH_PASS',flush=True)
