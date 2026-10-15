import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const preview=new URL('../../.preview/',import.meta.url);
const {ManagedProjectsIpc}=await import(new URL('packages/runtime/dist/index.js',preview));
const entry=fileURLToPath(new URL('../ipc-entry.py',import.meta.url));
const manager=new ManagedProjectsIpc({executable:process.env.PROJECTS_PYTHON,args:[entry],cwd:fileURLToPath(new URL('../../candidate/',import.meta.url)),entry_path:entry,
  entry_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex'),build_sha:process.env.B2_BUILD_SHA},process.env.DATA_ROOT);
await manager.start(15000);
const guardian=manager.managed.child.pid;
const child=execFileSync('ps',['-axo','pid=,ppid=,command='],{encoding:'utf8'}).split('\n').map(line=>/^\s*(\d+)\s+(\d+)\s+(.*)$/.exec(line)).find(match=>match&&Number(match[2])===guardian&&match[3].includes(entry));
if(!child)throw Error('MANAGED_CHILD_NOT_FOUND');
writeFileSync(process.argv[2],JSON.stringify({...manager.identity,guardian,child:Number(child[1])}),{mode:0o600});
const alive=setInterval(()=>{},1000);
for(const signal of ['SIGTERM','SIGINT'])process.once(signal,()=>{clearInterval(alive);void manager.stop().then(()=>process.exit(0));});
