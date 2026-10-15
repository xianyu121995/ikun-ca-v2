/** Run foreground under the sole shared heavy lock. No provider/network probes. */
import {spawnSync} from 'node:child_process';
import {mkdirSync,openSync,closeSync,writeFileSync,readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const runtime='release-integration/.runtime/night-b3';mkdirSync(runtime,{recursive:true,mode:0o700});
const log=openSync(runtime+'/build.log','a',0o600),results=[];
try{
 for(const args of [['--filter','@ikun/tracking-worker','build'],['--filter','@ikun/website','build'],['--filter','@ikun/website','typecheck']]){
  console.log('B3 integration pnpm '+args.join(' '));const started=Date.now();
  const result=spawnSync('pnpm',args,{cwd:process.cwd(),env:{...process.env,NEXT_TELEMETRY_DISABLED:'1'},stdio:['ignore',log,log]});
  results.push({args,exit_code:result.status,duration_ms:Date.now()-started});if(result.status!==0)throw Error('BUILD_STAGE_FAILED');
 }
 for(const [file,expected] of [['services/hunter-worker/dist/main.js','81499cd9d9d84d26131e111f9bbd8cf4c4a3776d4452a11b547ec178bb080206'],['services/tracking-worker/dist/main.js','b9275375891c1b3ba02a123ea09afb0a8233fb27a2918b7b9c925cce997265eb']]){
  if(createHash('sha256').update(readFileSync(file)).digest('hex')!==expected)throw Error('FROZEN_COMPILED_ENTRY_DRIFT');
 }
 console.log('B3 production build/typecheck and both compiled entry bindings PASS');
}catch(error){process.exitCode=1;console.log(String(error.message));}
finally{closeSync(log);writeFileSync(runtime+'/build-'+Date.now()+'.json',JSON.stringify({status:process.exitCode?'FAIL':'PASS',commands:results,log_sha256:createHash('sha256').update(readFileSync(runtime+'/build.log')).digest('hex')},null,2)+'\n',{mode:0o600});}
