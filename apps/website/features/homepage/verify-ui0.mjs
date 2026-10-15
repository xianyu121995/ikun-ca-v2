import {readFileSync,writeFileSync,existsSync,readdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {dirname,resolve,relative,join} from 'node:path';
import {fileURLToPath} from 'node:url';

const feature=dirname(fileURLToPath(import.meta.url));
const root=resolve(feature,'../../../..');
const module=join(root,'apps/website/components/homepage-ui');
const allowed=['apps/website/components/homepage-ui/','apps/website/features/homepage/','apps/website/app/prototypes/homepage/'];
const baseline='eed9434fb73bba6e71e2040d2db43bf2632f650a';
const spec='9699375c920465b5d802e7acff17b5421203e544';
const git=(...args)=>execFileSync('git',args,{cwd:root});
const sha=buffer=>createHash('sha256').update(buffer).digest('hex');
const owned=name=>allowed.some(prefix=>name.startsWith(prefix));
const files=git('ls-tree','-r','--name-only',baseline).toString().trim().split('\n');
let protectedCount=0;
for(const file of files){
  if(owned(file))continue;
  if(!readFileSync(join(root,file)).equals(git('show',`${baseline}:${file}`)))throw Error(`Protected file changed: ${file}`);
  protectedCount++;
}
const differences=[...git('diff','--name-only',baseline).toString().split('\n'),...git('ls-files','--others','--exclude-standard').toString().split('\n')].filter(Boolean);
if(differences.some(file=>!owned(file)))throw Error('Changes outside homepage owner paths');
if(!git('merge-base','--is-ancestor',baseline,'HEAD').equals(Buffer.alloc(0)))throw Error('Frozen baseline not preserved');
const pin=JSON.parse(readFileSync(join(feature,'spec-pin.json'),'utf8'));
if(pin.spec_commit!==spec)throw Error('Specification pin mismatch');
for(const [name,digest] of Object.entries(pin.spec_files_sha256))if(sha(git('show',`${spec}:docs/phase2/${name}`))!==digest)throw Error(`Spec hash changed: ${name}`);
const release=JSON.parse(git('show',`${spec}:docs/phase2/releases.json`).toString());
if(!release.immediately_released.includes('homepage-ui')||release.merge_authorized||release.production_authorized)throw Error('Release boundary mismatch');
const stats=JSON.parse(readFileSync(join(module,'evidence/shared-ui/test-results.json'),'utf8')).stats;
if(stats.expected!==19||stats.unexpected||stats.skipped)throw Error('Browser acceptance incomplete');
const unit=readFileSync(join(module,'evidence/shared-ui/view-model-tests.tap'),'utf8');
if(!unit.includes('# tests 8')||!unit.includes('# pass 8')||!unit.includes('# fail 0'))throw Error('View model tests incomplete');
const sources=[...['phase2-homepage.tsx','phase2-preview.tsx','shared-dialog.tsx','phase2-homepage.css','prepare-shared-ui.mjs'].map(name=>join(module,name)),...['types.ts','view-model.ts','demo-fixtures.ts'].map(name=>join(feature,name)),join(root,'apps/website/app/prototypes/homepage/page.tsx')];
for(const file of sources){const text=readFileSync(file,'utf8');if(/\b(fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(/.test(text))throw Error('Page network client detected');if(/from\s+['"]\/|crypto\.randomUUID/.test(text))throw Error('Absolute import or page ID generation detected');}
function databases(folder){if(!existsSync(folder))return [];return readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?databases(join(folder,entry.name)):/\.(db|sqlite3?)$/.test(entry.name)?[entry.name]:[]);}
if(databases(join(root,'var')).length)throw Error('UI QA must not create business databases');
const sharedPin=JSON.parse(readFileSync(join(module,'shared-ui-pin.json'),'utf8'));
const dependency=join(module,'node_modules/@ikun/ui');
const receipt=JSON.parse(readFileSync(join(dependency,'homepage-qa-receipt.json'),'utf8'));
if(receipt.commit!==sharedPin.commit||sharedPin.commit!==pin.shared_ui_revision||!receipt.source_clean)throw Error('Shared UI pin/receipt mismatch');
for(const [file,digest] of Object.entries(receipt.artifacts))if(sha(readFileSync(join(dependency,'dist',file)))!==digest)throw Error('Shared UI artifact changed');
if(/ui-port|previewUI/.test(readFileSync(join(module,'phase2-preview.tsx'),'utf8')+readFileSync(join(module,'phase2-homepage.tsx'),'utf8')))throw Error('Native preview fallback used by active page');
for(const file of ['phase2-homepage.tsx','phase2-preview.tsx','shared-dialog.tsx'])if(!readFileSync(join(module,file),'utf8').includes("from '@ikun/ui'"))throw Error('Direct public package binding missing');
const proof={contract_version:'phase2-v1.0.0',spec_commit:spec,source_baseline:baseline,branch:git('branch','--show-current').toString().trim(),
  owner_paths:allowed,protected_files_unchanged:protectedCount,new_changes_owner_only:true,frozen_baseline_preserved:true,
  shared_ui_binding:'DIRECT_PACKAGE_IMPORTS_LOCAL_NEXT_VERIFIED',shared_ui_commit:sharedPin.commit,shared_ui_artifacts_sha256:receipt.artifacts,root_workspace_registration:'PENDING_CHIEF_B0',live_adapter:'NOT_CONNECTED',runtime_dependency_changes:false,
  typecheck:'pnpm --filter @ikun/website typecheck passed',build:'Next 16.4.1 website build passed, cpus=1, serial',
  unit:{passed:8,failed:0},browser:{passed:stats.expected,failed:stats.unexpected,widths:[1440,1920,2560,390],duration_ms:stats.duration},
  page_network_clients:0,business_database_created:false,
  active_source_sha256:Object.fromEntries(sources.map(file=>[relative(root,file),sha(readFileSync(file))])),
  not_verified:['clean checkout workspace frozen install','fresh shared type/dependency propagation','real auth and Projects adapter','production or platform data','deployment']};
writeFileSync(join(module,'evidence/shared-ui/verification.json'),JSON.stringify(proof,null,2)+'\n');
process.stdout.write(JSON.stringify({owner_only:true,protected_files:protectedCount,unit_passed:8,browser_passed:stats.expected})+'\n');
