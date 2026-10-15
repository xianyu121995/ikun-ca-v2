/** Foreground integration build; the shared heavy lock must own this entire process group. */
import {spawnSync} from 'node:child_process';
import {mkdirSync,openSync,closeSync,writeFileSync,readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const runtime='release-integration/.runtime/night-b4';mkdirSync(runtime,{recursive:true,mode:0o700});
const log=openSync(runtime+'/build.log','a',0o600),results=[];
try{
 for(const args of [['install','--frozen-lockfile'],['build'],['--filter','@ikun/hunter-worker','build'],['typecheck'],['exec','node','release-integration/scripts/c0_regression.mjs']]){
  console.log('B4 integration pnpm '+args.join(' '));const started=Date.now();
  const result=spawnSync('pnpm',args,{cwd:process.cwd(),env:{...process.env,NEXT_TELEMETRY_DISABLED:'1'},stdio:['ignore',log,log]});
  results.push({args,exit_code:result.status,duration_ms:Date.now()-started});
  if(result.status!==0)throw Error('BUILD_STAGE_FAILED');
 }
 const entry=readFileSync('services/hunter-worker/dist/main.js');
 if(createHash('sha256').update(entry).digest('hex')!=='81499cd9d9d84d26131e111f9bbd8cf4c4a3776d4452a11b547ec178bb080206')throw Error('FROZEN_COMPILED_ENTRY_DRIFT');
 console.log('B4 integration build and original regressions PASS');
}catch(error){process.exitCode=1;console.log(String(error.message));}
finally{closeSync(log);writeFileSync(runtime+'/build.json',JSON.stringify({status:process.exitCode?'FAIL':'PASS',commands:results,log_sha256:createHash('sha256').update(readFileSync(runtime+'/build.log')).digest('hex')},null,2)+'\n',{mode:0o600});}
