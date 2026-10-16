/** C0-lite adaptation of the accepted B2 launcher: actual release, same B0 UDS manager. */
import {readFileSync,lstatSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ManagedProjectsIpc,spawnManaged} from '../packages/runtime/dist/index.js';
import {inspectAuthDatabase} from '../modules/auth/dist/src/database.js';
import {environment} from '../modules/auth/dist/src/config.js';
const root=resolve(fileURLToPath(new URL('..',import.meta.url)));
if(!process.env.DATA_ROOT||!process.env.PROJECTS_PYTHON)throw Error('EXPLICIT_ISOLATED_CONFIGURATION_REQUIRED');
// This additional direction stays in the owned 0600 web file, never launchd argv.
if(process.env.IKUN_TRACKING_INGEST_ENV_FILE){
  const path=process.env.IKUN_TRACKING_INGEST_ENV_FILE;
  if(path!==resolve(process.env.DATA_ROOT,'..','config/web.environment.json'))throw Error('OWNED_INGEST_ENV_REQUIRED');
  const info=lstatSync(path);
  if(!info.isFile()||info.uid!==process.getuid()||(info.mode&0o777)!==0o600||info.nlink!==1||info.size>65536)throw Error('PRIVATE_INGEST_ENV_REQUIRED');
  let token;
  try{token=JSON.parse(readFileSync(path,'utf8')).PROJECTS_INGEST_TRACKING_TOKEN;}catch{throw Error('INVALID_INGEST_ENV');}
  if(typeof token!=='string'||token.length<32||token.length>8192||!/^[!-~]+$/.test(token)||process.env.PROJECTS_INGEST_TRACKING_TOKEN!==undefined)throw Error('INVALID_INGEST_DIRECTION');
  process.env.PROJECTS_INGEST_TRACKING_TOKEN=token;
}
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
