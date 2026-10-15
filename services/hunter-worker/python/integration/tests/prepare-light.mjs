// Small unit-test transpilation only; no Next build, install, browser or long-running service.
import {execFileSync} from 'node:child_process';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const moduleRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),root=path.resolve(moduleRoot,'../../..');
const output=path.join(moduleRoot,'var/b4/light'),require=createRequire(path.join(root,'package.json')),ts=require('typescript');
const auth='f097bd4722155d5e689b8894956391ed7e5f2fa7';
function write(target,text){mkdirSync(path.dirname(target),{recursive:true});writeFileSync(target,text);}
function transpile(source,target){write(target,ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,verbatimModuleSyntax:false}}).outputText);}
write(path.join(output,'package.json'),'{"type":"module"}');
const files=execFileSync('git',['ls-tree','-r','--name-only',auth,'modules/auth/src'],{cwd:root,encoding:'utf8'}).trim().split('\n');
for(const file of files){const source=execFileSync('git',['show',auth+':'+file],{cwd:root,encoding:'utf8'});transpile(source,path.join(output,file.replace('/src/','/dist/src/').replace(/\.ts$/,'.js')));}
transpile(readFileSync(path.join(moduleRoot,'integration/website/lib/hunter.ts'),'utf8'),path.join(output,'apps/website/lib/hunter.js'));
const route='app/api/v1/hunter/[...path]/route.ts';
transpile(readFileSync(path.join(moduleRoot,'integration/website',route),'utf8').replace("'../../../../../lib/hunter'","'../../../../../lib/hunter.js'"),path.join(output,'apps/website',route.replace(/\.ts$/,'.js')));
console.log(output);
