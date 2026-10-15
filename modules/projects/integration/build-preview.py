"""Serial, reproducible local build and source receipt; no shared checkout writes."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('assembly',HERE/'prepare-preview.py');assembly=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembly)
ROOT=assembly.ROOT;PREVIEW=assembly.PREVIEW;ARTIFACTS=ROOT/'modules/projects/artifacts'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_inputs():
    files=[]
    for prefix in ('modules/projects/candidate/projects_service','modules/projects/candidate/tests','modules/projects/integration','schemas/projects'):
        for path in (ROOT/prefix).rglob('*'):
            if path.is_file() and path.suffix in ('.py','.ts','.tsx','.js','.mjs','.html','.css','.sql','.patch') and '__pycache__' not in path.parts:
                files.append(path)
    files.append(ROOT/'modules/projects/candidate/pyproject.toml')
    return {str(path.relative_to(ROOT)):digest(path) for path in sorted(files)}

def main():
    node=os.environ.get('B2_NODE') or shutil.which('node');pnpm=shutil.which('pnpm')
    if not node or not pnpm:raise RuntimeError('NODE24_AND_PNPM10_REQUIRED')
    version=subprocess.check_output([node,'--version'],text=True).strip()
    if not version.startswith('v24.'):raise RuntimeError('PINNED_NODE24_REQUIRED')
    if not (PREVIEW/'package.json').exists():assembly.main()
    # Regenerate only the explicitly reviewed UI inputs/patch in this disposable assembly.
    for relative in ('apps/website/components/homepage-ui','apps/website/features/homepage'):
        target=PREVIEW/relative
        if target.exists():shutil.rmtree(target)
    assembly.archive(assembly.PINS['homepage'],*[f'apps/website/components/homepage-ui/{name}' for name in ['reference-homepage.tsx','reference-editor.tsx','shared-dialog.tsx','reference-homepage.css']],
        *[f'apps/website/features/homepage/{name}.ts' for name in ['types','reference-types','reference-model','view-model']])
    patch_hash=assembly.patch_homepage()
    shutil.copytree(HERE/'website',PREVIEW/'apps/website',dirs_exist_ok=True)
    ARTIFACTS.mkdir(exist_ok=True)
    env={**os.environ,'PATH':str(Path(node).parent)+os.pathsep+os.environ.get('PATH','')}
    with (ARTIFACTS/'build.log').open('w') as log:
        for args in [[pnpm,'install','--frozen-lockfile'],[pnpm,'build:shared'],[pnpm,'--filter','@ikun/ui','build'],
                     [pnpm,'exec','tsc','-p','modules/auth/tsconfig.json'],[pnpm,'--filter','@ikun/website','build']]:
            result=subprocess.run(args,cwd=PREVIEW,env=env,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError('BUILD_FAILED: see modules/projects/artifacts/build.log')
    receipt={**assembly.PINS,'profile':'phase2-v1.0.0+auth-b1-final-v2+projects-home-v1','baseline_commit':'7f8a4610b4dcdda1f0785c2fc3c73a18ebdeb35f',
        'node':version,'lock_sha256':digest(PREVIEW/'pnpm-lock.yaml'),'ui_patch_sha256':patch_hash,'inputs':source_inputs(),
        'next_build_id':(PREVIEW/'apps/website/.next/BUILD_ID').read_text().strip(),'build_log_sha256':digest(ARTIFACTS/'build.log')}
    receipt['source_set_sha256']=hashlib.sha256(json.dumps(receipt['inputs'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (ARTIFACTS/'build-inputs.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n')
    print('B2_BUILD_PASS '+receipt['source_set_sha256'])

if __name__=='__main__':main()
