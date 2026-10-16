/** Foreground only, under the shared heavy lock. No worker build or external calls. */
import {spawnSync} from 'node:child_process';
import {mkdirSync,openSync,closeSync,readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const root='release-integration/.runtime/tracking-ingest';mkdirSync(root,{mode:0o700,recursive:true});
const path=root+'/build-'+Date.now()+'.log',log=openSync(path,'wx',0o600),commands=[];
try{
 for(const args of [['--filter','@ikun/website','build'],['--filter','@ikun/website','typecheck']]){
  console.log('Receiver integration pnpm '+args.join(' '));const started=Date.now();
  const result=spawnSync('pnpm',args,{env:{...process.env,NEXT_TELEMETRY_DISABLED:'1'},stdio:['ignore',log,log]});
  commands.push({args,exit_code:result.status,duration_ms:Date.now()-started});if(result.status!==0)throw Error('BUILD_STAGE_FAILED');
 }
 for(const [file,hash] of [['services/hunter-worker/dist/main.js','81499cd9d9d84d26131e111f9bbd8cf4c4a3776d4452a11b547ec178bb080206'],['services/tracking-worker/dist/main.js','b9275375891c1b3ba02a123ea09afb0a8233fb27a2918b7b9c925cce997265eb']])if(createHash('sha256').update(readFileSync(file)).digest('hex')!==hash)throw Error('FROZEN_WORKER_COMPILED_DRIFT');
 console.log('RECEIVER_PRODUCTION_BUILD_TYPECHECK_PASS');
}catch(e){process.exitCode=1;console.log(e.message);}
finally{closeSync(log);writeFileSync(path+'.json',JSON.stringify({state:process.exitCode?'FAIL':'PASS',commands,log:path,log_sha256:createHash('sha256').update(readFileSync(path)).digest('hex')},null,2)+'\n',{mode:0o600});}
