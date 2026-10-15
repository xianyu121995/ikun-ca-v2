/** Local website-owner startup candidate. Explicitly migrated stores required. */
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const here=fileURLToPath(new URL('.',import.meta.url));
const preview=resolve(here,'../.preview');
const {ManagedProjectsIpc,spawnManaged}=await import(pathToFileURL(join(preview,'packages/runtime/dist/index.js')));
const {inspectAuthDatabase}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/database.js')));
const {environment}=await import(pathToFileURL(join(preview,'modules/auth/dist/src/config.js')));
if(!process.env.DATA_ROOT||!process.env.PROJECTS_PYTHON)throw Error('EXPLICIT_ISOLATED_CONFIGURATION_REQUIRED');
if(!/^[a-f0-9]{40}$/.test(process.env.B2_BUILD_SHA??''))throw Error('EXPLICIT_PROJECTS_BUILD_SHA_REQUIRED');
inspectAuthDatabase(environment());
const entry=join(here,'ipc-entry.py');
const manager=new ManagedProjectsIpc({executable:process.env.PROJECTS_PYTHON,args:[entry],cwd:resolve(here,'../candidate'),entry_path:entry,
  entry_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex'),build_sha:process.env.B2_BUILD_SHA},process.env.DATA_ROOT);
let next;let stopping=false;
async function stop(){if(stopping)return;stopping=true;await next?.stop();await manager.stop();}
for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>{void stop().then(()=>process.exit(0));});
try{
  await manager.start(15000);
  next=spawnManaged(process.execPath,[join(preview,'apps/website/node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port',process.env.PORT??'3109'],{
    cwd:join(preview,'apps/website'),env:{...process.env,IKUN_PROJECTS_IPC_SOCKET:manager.identity.socketPath,IKUN_PROJECTS_IPC_TOKEN:manager.identity.token,IKUN_PROJECTS_BUILD_SHA:manager.identity.buildSha},inheritOutput:true});
  next.child.once('exit',()=>{void stop().then(()=>process.exit(0));});
}catch(error){await stop();throw error;}
