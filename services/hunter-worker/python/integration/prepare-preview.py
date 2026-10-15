"""Ignored B4 composition. Preparation only; build/browser require the shared heavy lock."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
MODULE=HERE.parent
ROOT=MODULE.parents[2]
PREVIEW=MODULE/'var/b4/preview'
PINS={'release':'63e8a2857241c6a76226f21435e40db9736a1e7e','spec':'9699375c920465b5d802e7acff17b5421203e544',
 'b0':'85be3bd6dce25d82033b6cb1a7157aaa39bd571e','auth':'f097bd4722155d5e689b8894956391ed7e5f2fa7','auth_increment_review':'1d56ef2f003c531574e41fe079c70510ac6ed437','projects':'cc95dc27852d056457ca0582cff64a88c0eab1d4','projects_constructor_review':'967f3098e84de7e299d970019d56b571ac63de94',
 'ui':'486294ac3255b08fdb13a307ee15f96c571020d9','hunter_ui':'08065d700239b20fb4c887bbd0c85321904687f8'}
def export(commit,*paths):
    data=subprocess.check_output(['git','archive',commit,*paths],cwd=ROOT)
    subprocess.run(['tar','-x','-C',str(PREVIEW)],input=data,check=True)
def prepare():
    if (PREVIEW/'package.json').exists():raise RuntimeError('preview_exists_preserve_evidence_choose_new_explicit_path')
    PREVIEW.mkdir(parents=True,exist_ok=True)
    export(PINS['b0']);export(PINS['ui'],'packages/ui')
    refresh()
def refresh():
    # Refresh only the disposable assembly from immutable dependencies and our candidate.
    export(PINS['auth'],'modules/auth/src','modules/auth/tsconfig.json','modules/auth/integration/website','schemas/auth')
    export(PINS['hunter_ui'],'apps/website/features/hunter-discovery')
    export(PINS['projects'],'modules/projects/integration/website/lib/projects.ts')
    shutil.copytree(PREVIEW/'modules/auth/integration/website',PREVIEW/'apps/website',dirs_exist_ok=True)
    shutil.copytree(HERE/'website',PREVIEW/'apps/website',dirs_exist_ok=True)
    shutil.copyfile(PREVIEW/'modules/projects/integration/website/lib/projects.ts',PREVIEW/'apps/website/lib/projects.ts')
    page=PREVIEW/'apps/website/app/hunter/page.tsx'
    page.write_text("import {projectsAuth} from '../../lib/projects';\n"+page.read_text().replace('  const session=','  projectsAuth();\n  const session=').replace('<HunterController session=','<HunterController fixture session='))
    probe=PREVIEW/'apps/website/app/internal/v1/hunter-action-probe/page.tsx';probe.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(HERE/'tests/fixtures/action-probe.tsx',probe)
    # Candidate-only command and event mounts; final multi-source gateway remains C0 ownership.
    for route,source in [('app/api/v1/commands/[id]/route.ts',"import {hunterCommandRoute} from '../../../../../lib/hunter';\nexport async function GET(request:Request,context:{params:Promise<{id:string}>}){return hunterCommandRoute(request,(await context.params).id);}\n"),
                         ('app/api/v1/events/stream/route.ts',"export {hunterEventsRoute as GET} from '../../../../../lib/hunter';\n")]:
        path=PREVIEW/'apps/website'/route;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source)
    package=PREVIEW/'apps/website/package.json';config=json.loads(package.read_text());config['dependencies']['@ikun/ui']='workspace:*';package.write_text(json.dumps(config,indent=2)+'\n')
    shutil.copyfile(PREVIEW/'config/b0/pnpm-ui-lock.yaml',PREVIEW/'pnpm-lock.yaml')
    patch=HERE/'patches/hunter-live.patch'
    relative=str(PREVIEW.relative_to(ROOT))
    for args in (['git','apply','--check','--directory='+relative,str(patch)],['git','apply','--directory='+relative,str(patch)]):subprocess.run(args,cwd=ROOT,check=True)
    inputs={'pins':PINS,'ui_patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
      'candidate_files_sha256':{str(p.relative_to(MODULE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((HERE/'website').rglob('*')) if p.is_file()},
      'patched_ui_files_sha256':{str(p.relative_to(PREVIEW)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((PREVIEW/'apps/website/features/hunter-discovery/v3').glob('*')) if p.name in ('App.tsx','model.ts')},
      'projects_helper_sha256':hashlib.sha256((PREVIEW/'apps/website/lib/projects.ts').read_bytes()).hexdigest(),
      'projects_auth_policy_exercised_in_hunter_page':True,'source_receiving':False,'provider_io':False,'preview_only_fixture_label':True}
    (PREVIEW/'b4-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    print(PREVIEW)
if __name__=='__main__':prepare()
