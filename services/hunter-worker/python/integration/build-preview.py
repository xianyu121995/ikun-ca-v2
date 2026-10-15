"""Full serial build. Do not run during the C0-lite priority hold."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('b4_assembly',HERE/'prepare-preview.py');assembly=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembly)
if not (assembly.PREVIEW/'package.json').exists():assembly.prepare()
else:assembly.refresh()
evidence=assembly.MODULE/'var/b4/evidence';evidence.mkdir(exist_ok=True)
env={key:os.environ[key] for key in ('PATH','HOME','TMPDIR','LANG','SHELL','COREPACK_HOME','PNPM_HOME') if key in os.environ}
env['NEXT_TELEMETRY_DISABLED']='1'
with (evidence/'build.log').open('w') as log:
    subprocess.run(['pnpm','--filter','@ikun/hunter-worker','build'],cwd=assembly.ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    for command in [['pnpm','install','--offline','--frozen-lockfile','--store-dir',str(assembly.ROOT/'.pnpm-store')],['pnpm','build:shared'],['pnpm','--filter','@ikun/ui','build'],['pnpm','exec','tsc','-p','modules/auth/tsconfig.json'],['pnpm','--filter','@ikun/website','build']]:
        subprocess.run(command,cwd=assembly.PREVIEW,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
receipt={**json.loads((assembly.PREVIEW/'b4-inputs.json').read_text()),'next_build_id':(assembly.PREVIEW/'apps/website/.next/BUILD_ID').read_text().strip(),'status':'passed'}
(evidence/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print('B4_PREVIEW_BUILD_PASS')
