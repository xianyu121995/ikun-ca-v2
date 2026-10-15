/** Foreground C0-lite build; invoke only through the shared heavy-lock wrapper. */
import {spawnSync} from 'node:child_process';
import {mkdirSync,writeFileSync,openSync,closeSync,readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
const root=process.cwd();
const runtime=resolve(root,'release-integration/.runtime/c0-lite');
mkdirSync(runtime,{recursive:true,mode:0o700});
const log=openSync(resolve(runtime,'build.log'),'a',0o600);
const receipt={started_at:new Date().toISOString(),commands:[],result:'RUNNING'};
const env={...process.env,NEXT_TELEMETRY_DISABLED:'1'};
try{
  for(const args of [['install','--frozen-lockfile'],['build'],['typecheck'],['exec','node','release-integration/scripts/c0_regression.mjs']]){
    const started=Date.now();console.log('C0-lite pnpm '+args.join(' '));
    const result=spawnSync('pnpm',args,{cwd:root,env,stdio:['ignore',log,log]});
    receipt.commands.push({argv:['pnpm',...args],exit_code:result.status,duration_ms:Date.now()-started});
    if(result.status!==0)throw new Error('BUILD_STAGE_FAILED: '+args[0]);
  }
  receipt.result='PASS';
}catch(error){receipt.result='FAIL';receipt.reason=String(error.message);process.exitCode=1;}
finally{
  closeSync(log);receipt.finished_at=new Date().toISOString();
  receipt.log_sha256=createHash('sha256').update(readFileSync(resolve(runtime,'build.log'))).digest('hex');
  const output=resolve(root,'release-integration/c0-lite/evidence/build-attempt-'+Date.now()+'.json');
  writeFileSync(output,JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({result:receipt.result,receipt:output}));
}
