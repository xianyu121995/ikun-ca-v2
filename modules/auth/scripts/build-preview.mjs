import {readFileSync,writeFileSync,cpSync,existsSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join,resolve,dirname} from 'node:path';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const manifest=JSON.parse(readFileSync(join(root,'modules/auth/test-results/b1-preview.json')));
const store=join(root,'modules/auth/test-results/pnpm-store');
if(!existsSync(store)) {
  const mainStore=execFileSync('git',['rev-parse','--git-common-dir'],{cwd:root,encoding:'utf8'}).trim();
  const source=join(dirname(resolve(root,mainStore)),'.pnpm-store');
  // Read-only cache source; all package-manager writes stay in this module's private cache.
  cpSync(source,store,{recursive:true,dereference:false});
}
const env={...process.env,PATH:`${fileURLToPath(new URL('.',`file://${process.execPath}`))}:${process.env.PATH}`,CI:'true',NEXT_TELEMETRY_DISABLED:'1'};
let log='';
for(const args of [['install','--offline','--ignore-scripts','--frozen-lockfile','--store-dir',store],
  ...['@ikun/contracts','@ikun/runtime','@ikun/ui','@ikun/website'].map(name=>['--filter',name,'build'])]) {
  try {log+=execFileSync('pnpm',args,{cwd:manifest.preview,env,encoding:'utf8',maxBuffer:8*1024*1024,stdio:['ignore','pipe','pipe']});}
  catch(error) {log+=error.stdout?.toString()??'';log+=error.stderr?.toString()??'';writeFileSync(join(root,'modules/auth/test-results/b1-build.log'),log);throw error;}
}
writeFileSync(join(root,'modules/auth/test-results/b1-build.log'),log);
writeFileSync(join(root,'modules/auth/test-results/b1-build.json'),JSON.stringify({passed:true,manifest,serial_build:true,offline_frozen_install:true},null,2)+'\n');
console.log('B1 fixed-B0 Next production build PASS');
