/** C0-lite adaptation of the accepted B2 launcher: actual release, same B0 UDS manager. */
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ManagedProjectsIpc,spawnManaged} from '../packages/runtime/dist/index.js';
import {inspectAuthDatabase} from '../modules/auth/dist/src/database.js';
import {environment} from '../modules/auth/dist/src/config.js';
const root=resolve(fileURLToPath(new URL('..',import.meta.url)));
if(!process.env.DATA_ROOT||!process.env.PROJECTS_PYTHON)throw Error('EXPLICIT_ISOLATED_CONFIGURATION_REQUIRED');
const build=process.env.IKUN_RELEASE_SHA;
if(!/^[a-f0-9]{40}$/.test(build??''))throw Error('EXPLICIT_RELEASE_SHA_REQUIRED');
if(process.env.IKUN_AUTH_ORIGIN?.startsWith('https:')&&process.env.IKUN_AUTH_DEV==='1')throw Error('SECURE_COOKIE_REQUIRED');
inspectAuthDatabase(environment());
const entry=join(root,'modules/projects/integration/ipc-entry.py');
const manager=new ManagedProjectsIpc({executable:process.env.PROJECTS_PYTHON,args:[entry],cwd:join(root,'modules/projects/candidate'),entry_path:entry,
  entry_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex'),build_sha:build},process.env.DATA_ROOT);
let next;let stopping=false;
async function stop(){if(stopping)return;stopping=true;await next?.stop();await manager.stop();}
for(const sig of ['SIGINT','SIGTERM'])process.once(sig,()=>{void stop().then(()=>process.exit(0));});
try{
  await manager.start(15000);
  next=spawnManaged(process.execPath,[join(root,'apps/website/node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',process.env.PORT??'4000'],{
    cwd:join(root,'apps/website'),env:{...process.env,NODE_ENV:'production',NEXT_TELEMETRY_DISABLED:'1',IKUN_PROJECTS_IPC_SOCKET:manager.identity.socketPath,IKUN_PROJECTS_IPC_TOKEN:manager.identity.token,IKUN_PROJECTS_BUILD_SHA:manager.identity.buildSha},inheritOutput:true});
  next.child.once('exit',()=>{void stop().then(()=>process.exit(0));});
}catch(error){await stop();throw error;}
