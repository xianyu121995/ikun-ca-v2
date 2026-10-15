import {readFileSync,writeFileSync,existsSync,readdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {dirname,resolve,relative,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const feature=dirname(fileURLToPath(import.meta.url)),root=resolve(feature,'../../../..'),ui=join(root,'apps/website/components/homepage-ui');
const allowed=['apps/website/components/homepage-ui/','apps/website/features/homepage/','apps/website/app/prototypes/homepage/'];
const baseline='eed9434fb73bba6e71e2040d2db43bf2632f650a',spec='9699375c920465b5d802e7acff17b5421203e544';
const git=(...args)=>execFileSync('git',args,{cwd:root}),sha=buffer=>createHash('sha256').update(buffer).digest('hex'),owned=name=>allowed.some(prefix=>name.startsWith(prefix));
let protectedCount=0;
for(const file of git('ls-tree','-r','--name-only',baseline).toString().trim().split('\n')){if(owned(file))continue;if(!readFileSync(join(root,file)).equals(git('show',`${baseline}:${file}`)))throw Error(`Protected file changed: ${file}`);protectedCount++;}
const differences=[...git('diff','--name-only',baseline).toString().split('\n'),...git('ls-files','--others','--exclude-standard').toString().split('\n')].filter(Boolean);
if(differences.some(file=>!owned(file)))throw Error('Changes outside homepage owner paths');
git('merge-base','--is-ancestor',baseline,'HEAD');
const pin=JSON.parse(readFileSync(join(feature,'spec-pin.json'),'utf8'));
if(pin.spec_commit!==spec)throw Error('Specification pin mismatch');
for(const [name,digest] of Object.entries(pin.spec_files_sha256))if(sha(git('show',`${spec}:docs/phase2/${name}`))!==digest)throw Error(`Spec hash changed: ${name}`);
const stats=JSON.parse(readFileSync(join(ui,'evidence/html-v2/test-results.json'),'utf8')).stats;
if(stats.expected!==42||stats.unexpected||stats.skipped||stats.flaky)throw Error('Browser acceptance incomplete');
const unit=readFileSync(join(ui,'evidence/html-v2/model-tests.tap'),'utf8');
if(!unit.includes('# tests 16')||!unit.includes('# pass 16')||!unit.includes('# fail 0'))throw Error('Model acceptance incomplete');
const build=readFileSync(join(ui,'evidence/html-v2/build.log'),'utf8');
if(!build.includes('✓ Compiled successfully')||!build.includes('/prototypes/homepage/html'))throw Error('Final routes were not built');
const typecheck=readFileSync(join(ui,'evidence/html-v2/typecheck.log'),'utf8');if(!typecheck.includes('tsc --noEmit')||/error TS\d/.test(typecheck))throw Error('Typecheck incomplete');
const reference=JSON.parse(readFileSync(join(ui,'final-reference.json'),'utf8'));
if(sha(readFileSync(join(root,reference.final_html)))!==reference.final_html_sha256)throw Error('Final HTML digest mismatch');
const sources=[...['reference-homepage.tsx','reference-editor.tsx','reference-homepage.css','phase2-preview.tsx','shared-dialog.tsx','prototype/ikun-home-ui-hourly-date-filter.html'].map(name=>join(ui,name)),...['reference-types.ts','reference-model.ts','reference-fixtures.ts','types.ts','view-model.ts'].map(name=>join(feature,name)),...['page.tsx','html/route.ts'].map(name=>join(root,'apps/website/app/prototypes/homepage',name))];
for(const file of sources){const text=readFileSync(file,'utf8');if(/\b(fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(/.test(text))throw Error('Page network client detected');if(/from\s+['"]\/|crypto\.randomUUID/.test(text))throw Error('Absolute import or canonical ID generation detected');}
function databases(folder){if(!existsSync(folder))return [];return readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?databases(join(folder,entry.name)):/\.(db|sqlite3?)$/.test(entry.name)?[entry.name]:[]);}
if(databases(join(root,'var')).length)throw Error('UI QA must not create business databases');
const sharedPin=JSON.parse(readFileSync(join(ui,'shared-ui-pin.json'),'utf8')),dependency=join(ui,'node_modules/@ikun/ui');
const receipt=JSON.parse(readFileSync(join(dependency,'homepage-qa-receipt.json'),'utf8'));
if(receipt.commit!==sharedPin.commit||sharedPin.commit!==pin.shared_ui_revision||!receipt.source_clean)throw Error('Shared UI pin mismatch');
for(const [file,digest] of Object.entries(receipt.artifacts))if(sha(readFileSync(join(dependency,'dist',file)))!==digest)throw Error('Shared UI artifact changed');
for(const name of ['reference-homepage.tsx','reference-editor.tsx','phase2-preview.tsx','shared-dialog.tsx'])if(!readFileSync(join(ui,name),'utf8').includes("from '@ikun/ui'"))throw Error('Public package binding missing');
const proof={status:'LOCAL_UI_ACCEPTANCE_PASSED_REAL_DATA_NOT_CONNECTED',design_baseline:reference.design_baseline,input_sha256:reference.input_sha256,final_html_sha256:reference.final_html_sha256,branch:git('branch','--show-current').toString().trim(),owner_paths:allowed,protected_files_unchanged:protectedCount,changes_owner_only:true,spec_commit:spec,shared_ui_commit:sharedPin.commit,root_workspace_registration:'PENDING_CHIEF_B0',tests:{browser_passed:stats.expected,browser_failed:stats.unexpected,model_passed:16,model_failed:0,widths:[1440,1920,2560,390]},typecheck:'PASS',next_build:'PASS',page_network_clients:0,business_database_created:false,live_api_connected:false,active_source_sha256:Object.fromEntries(sources.map(file=>[relative(root,file),sha(readFileSync(file))])),not_verified:['fresh checkout shared dependency installation','real auth and Projects adapter','server persistence and business authorization','deployment or production integration','human final acceptance']};
writeFileSync(join(ui,'evidence/html-v2/verification.json'),JSON.stringify(proof,null,2)+'\n');
process.stdout.write(JSON.stringify({protected_files:protectedCount,owner_only:true,browser_passed:stats.expected,model_passed:16})+'\n');
