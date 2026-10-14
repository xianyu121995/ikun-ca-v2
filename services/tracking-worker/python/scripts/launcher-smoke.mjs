import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root=fileURLToPath(new URL('../../../..',import.meta.url));
const scratch=await realpath(await mkdtemp(resolve(tmpdir(),'ikun-tracking-launcher-')));
const port=await new Promise(done=>{const server=createServer();server.listen(0,'127.0.0.1',()=>{const p=server.address().port;server.close(()=>done(p));});});
const config=resolve(scratch,'config.json');
await writeFile(config,JSON.stringify({db_path:resolve(scratch,'tracking.db'),port,remote_enabled:false}));
const child=spawn(process.execPath,[resolve(root,'scripts/service.mjs'),'tracking','start'],{
  cwd:root,env:{...process.env,IKUN_TRACKING_CONFIG:config,IKUN_TRACKING_ADMIN_TOKEN:'launcher-test-credential-xxxxxxxxxxxxxx'},stdio:'ignore'
});
try{
  let healthy=false;
  for(let i=0;i<100;i++){try{if((await fetch(`http://127.0.0.1:${port}/health/ready`)).ok){healthy=true;break;}}catch{}await new Promise(r=>setTimeout(r,50));}
  assert.equal(healthy,true);
  const status=await(await fetch(`http://127.0.0.1:${port}/api/tracking/status`,{headers:{Authorization:'Bearer launcher-test-credential-xxxxxxxxxxxxxx'}})).json();
  assert.equal(status.engine.alive,true);
  assert.equal(status.remote_enabled,false);
  assert.equal(status.engine.connection,'disconnected');
  child.kill('SIGTERM');
  const code=await new Promise(done=>child.once('exit',done));
  assert.equal(code,0);
  process.stdout.write('Service launcher smoke passed: existing start:tracking entry, independent engine/API, remote disabled, SIGTERM exit 0.\n');
}finally{if(child.exitCode===null)child.kill('SIGTERM');}
