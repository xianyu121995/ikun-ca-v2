/** Run after committing reviewed sources; all artifacts remain ignored and credential-free. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const root=new URL('../../../',import.meta.url),base='48d9dd4d5f955f9e1db7709e5c66c65826fb5ab0';
const git=(...args)=>execFileSync('git',args,{cwd:root,encoding:'utf8'}).trim();
const sha=value=>createHash('sha256').update(value).digest('hex');
const read=name=>readFileSync(new URL(name,root));
assert.equal(git('status','--porcelain'),'','commit all reviewed changes first');
const preview=JSON.parse(read('modules/auth/test-results/b1-preview.json'));
const build=JSON.parse(read('modules/auth/test-results/b1-build.json'));
const browser=JSON.parse(read('modules/auth/test-results/b1-final-v2-browser.json'));
assert.equal(build.passed,true);assert.equal(browser.passed,true);
assert.deepEqual(build.manifest.inputs,preview.inputs);assert.deepEqual(browser.source_inputs,preview.inputs);
for(const [path,hash] of Object.entries(preview.inputs)) {
 assert.equal(sha(read(path)),hash,path+' changed after preview');
 assert.equal(sha(execFileSync('git',['show','HEAD:'+path],{cwd:root})),hash,path+' differs from commit');
}
const paths=git('diff','--name-only',base,'HEAD').split('\n').filter(Boolean);
assert.ok(paths.length>0&&paths.every(path=>path.startsWith('modules/auth/')),'auth-only boundary');
const regression=read('modules/auth/test-results/b1-final-v2-regression.log').toString();
const tests=Number(regression.match(/(?:ℹ|#) tests (\d+)/)?.[1]);
const passed=Number(regression.match(/(?:ℹ|#) pass (\d+)/)?.[1]);
assert.equal(tests,54);assert.equal(passed,54);assert.match(regression,/(?:ℹ|#) fail 0/);assert.match(regression,/(?:ℹ|#) skipped 0/);
const files=['b1-final-v2-regression.log','b1-build.log','b1-build.json','b1-preview.json','b1-final-v2-browser.json','b1-final-v2-browser-run.log'];
const receipt={final_commit_sha:git('rev-parse','HEAD'),baseline_commit:base,branch:git('branch','--show-current'),
 requirement:'user-final-B1-20261015',b0_commit:preview.b0_commit,ui_commit:preview.ui_commit,
 tests:{total:tests,passed,failed:0,skipped:0},next_build:'passed',chromium:'passed',
 browser_artifacts:browser.artifacts,source_inputs_equal_build_browser_and_commit:true,
 artifact_hashes:Object.fromEntries(files.map(name=>[name,sha(read('modules/auth/test-results/'+name))])),
 allowed_changed_paths:paths,git_status_short:'',merge:false,push:false,production:false,
 limitations:'Auth-only isolated Next acceptance. Chief owns real business/IPC/Cloudflare/production integration.'};
writeFileSync(new URL('modules/auth/test-results/b1-final-v2-receipt.json',root),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({commit:receipt.final_commit_sha,tests:receipt.tests,next:receipt.next_build,chromium:receipt.chromium,boundary:'auth-only',clean:true}));
