/** B1-only disposable assembly. Does not receive or modify the real website. */
import {cpSync,existsSync,mkdirSync,readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const B0='85be3bd6dce25d82033b6cb1a7157aaa39bd571e',UI='486294ac3255b08fdb13a307ee15f96c571020d9';
const preview=join(root,'modules/auth/test-results',`b1-preview-${Date.now()}`);
mkdirSync(preview,{recursive:true});
const git=args=>execFileSync('git',args,{cwd:root,maxBuffer:16*1024*1024});
execFileSync('tar',['-x','-C',preview],{input:git(['archive',B0])});
execFileSync('tar',['-x','-C',preview],{input:git(['archive',UI,'packages/ui'])});
const packagePath=join(preview,'apps/website/package.json');
const website=JSON.parse(readFileSync(packagePath));website.dependencies['@ikun/ui']='workspace:*';
writeFileSync(packagePath,JSON.stringify(website,null,2)+'\n');
cpSync(join(preview,'config/b0/pnpm-ui-lock.yaml'),join(preview,'pnpm-lock.yaml'));
for(const name of ['src','dist','tsconfig.json']) cpSync(join(root,'modules/auth',name),join(preview,'modules/auth',name),{recursive:true});
cpSync(join(root,'modules/auth/integration/website'),join(preview,'apps/website'),{recursive:true});
cpSync(join(root,'modules/auth/integration/preview-only'),join(preview,'apps/website'),{recursive:true});
const inputs={};
function record(directory) {for(const entry of readdirSync(join(root,directory),{withFileTypes:true})) {
  const name=directory+'/'+entry.name;if(entry.isDirectory()) record(name);
  else inputs[name]=createHash('sha256').update(readFileSync(join(root,name))).digest('hex');
}}
for(const name of ['modules/auth/src','modules/auth/integration']) record(name);
const manifest={preview,b0_commit:B0,ui_commit:UI,spec_commit:'9699375c920465b5d802e7acff17b5421203e544',
  scope:'ikun-main',auth_maximum_version:2,lock_sha256:createHash('sha256').update(readFileSync(join(preview,'pnpm-lock.yaml'))).digest('hex'),inputs};
writeFileSync(join(root,'modules/auth/test-results/b1-preview.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(preview);
