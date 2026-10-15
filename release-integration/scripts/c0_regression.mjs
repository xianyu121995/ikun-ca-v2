/** B1's admission fixture points at this actually-built B0 runtime, never a copied preview. */
import {mkdirSync,writeFileSync,readFileSync,existsSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
const root=process.cwd();
const path=resolve(root,'modules/auth/test-results/b1-preview.json');
if(existsSync(path)&&JSON.parse(readFileSync(path,'utf8')).preview!==root)throw Error('EXISTING_TEST_RECEIPT_PRESERVED');
mkdirSync(resolve(root,'modules/auth/test-results'),{recursive:true,mode:0o700});
if(!existsSync(path))writeFileSync(path,JSON.stringify({preview:root,profile:'c0-lite-actual-received-runtime',
  runtime_source_sha256:createHash('sha256').update(readFileSync('packages/runtime/src/stores.ts')).digest('hex')})+'\n',{mode:0o600});
const out=resolve(root,'release-integration/.runtime/c0-lite/regression.log');
const results=[];
for(const command of [['pnpm','test:auth'],[process.execPath,'--import','./release-integration/scripts/permission-fixture.mjs','--test','tests/b0-launch.test.mjs','tests/b0-managed.test.mjs','tests/b0-stores.test.mjs','tests/foundation.test.mjs']]){
 const result=spawnSync(command[0],command.slice(1),{encoding:'utf8',maxBuffer:8*1024*1024});
 writeFileSync(out,(existsSync(out)?readFileSync(out,'utf8'):'')+result.stdout+result.stderr,{mode:0o600});
 results.push({argv:command,exit_code:result.status});
 if(result.status!==0){process.exitCode=1;break;}
}
const receipt=resolve(root,'release-integration/c0-lite/evidence/regression-attempt-'+Date.now()+'.json');
writeFileSync(receipt,JSON.stringify({commands:results,fixture_location:path,fixture_is_actual_runtime:true,
 log_sha256:createHash('sha256').update(readFileSync(out)).digest('hex')},null,2)+'\n');
console.log(JSON.stringify({receipt,commands:results}));
