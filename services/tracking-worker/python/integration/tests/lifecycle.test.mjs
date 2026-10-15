/** Lightweight non-browser B0-managed entry regression. All PIDs are this test's private tree. */
import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtempSync,realpathSync,writeFileSync,readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {createServer} from 'node:net';
const moduleRoot=fileURLToPath(new URL('../../',import.meta.url)),root=join(moduleRoot,'.b3/preview');
const scratch=realpathSync(mkdtempSync('/private/tmp/ik-b3-life-')),python=join(moduleRoot,'.venv/bin/python');
const reserve=createServer();await new Promise(r=>reserve.listen(0,'127.0.0.1',r));const port=reserve.address().port;await new Promise(r=>reserve.close(r));
const config=join(scratch,'config.json');writeFileSync(config,JSON.stringify({db_path:join(scratch,'tracking/tracking.db'),port,remote_enabled:false}));
const env={PATH:process.env.PATH,HOME:process.env.HOME,DATA_ROOT:scratch,IKUN_TRACKING_CONFIG:config,IKUN_TRACKING_PYTHON:python,TRACKING_API_TOKEN:'lifecycle-fixture-direction-xxxxxxxxxxxx'};
execFileSync(python,['-m','tracking.cli','init','--config',config],{cwd:moduleRoot,env});
let child;
const children=[];
async function until(fn,seconds=12){const end=Date.now()+seconds*1000;while(Date.now()<end){try{if(await fn())return;}catch{}await new Promise(r=>setTimeout(r,100));}throw Error('PROCESS_CONDITION_TIMEOUT');}
function tree(pid){const rows=execFileSync('ps',['-axo','pid=,ppid=,stat='],{encoding:'utf8'}).trim().split('\n').map(r=>r.trim().split(/\s+/));const result=new Set([pid]);let size;do{size=result.size;for(const r of rows)if(result.has(+r[1]))result.add(+r[0]);}while(size!==result.size);return [...result];}
function alive(pid){try{return !/Z/.test(execFileSync('ps',['-o','stat=','-p',String(pid)],{encoding:'utf8'}).trim());}catch{return false;}}
async function start(){child=spawn(process.execPath,(process.argv.includes('--source')?[join(root,'services/tracking-worker/src/main.ts')]:[join(root,'scripts/service.mjs'),'tracking','start']),{cwd:root,env,stdio:'ignore'});children.push(child);await until(async()=>(await fetch(`http://127.0.0.1:${port}/health/ready`)).ok);}
try{
 await start();let state=await(await fetch(`http://127.0.0.1:${port}/internal/v1/status`,{headers:{authorization:'Bearer '+env.TRACKING_API_TOKEN}})).json();assert.equal(state.data.alive,true);assert.equal(state.data.external_collection_enabled,false);assert.equal(state.data.source_state,"unconfigured");
 child.kill('SIGTERM');assert.equal(await new Promise(r=>child.once('exit',r)),0);
 await start();const pids=tree(child.pid);assert.ok(pids.length>=(process.argv.includes('--source')?3:4));child.kill('SIGKILL');await new Promise(r=>child.once('exit',r));await until(()=>pids.every(pid=>!alive(pid)),15);
 await start();child.kill('SIGTERM');assert.equal(await new Promise(r=>child.once('exit',r)),0);
 console.log('B3_LIFECYCLE_PASS explicit init, B0 entry, SIGTERM, parent SIGKILL/private tree reaping, restart');
}finally{for(const p of children)if(p.exitCode===null&&p.signalCode===null)p.kill('SIGTERM');}
