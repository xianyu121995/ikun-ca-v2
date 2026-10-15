// Read a pinned public UI commit; build a private dependency under this prototype only.
import {execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(dir,'../../../../..');
const source=process.env.IKUN_UI_SOURCE||root;
const pin=JSON.parse(fs.readFileSync(path.join(dir,'reference/provenance.json'))).sharedUiCommit;
const target=path.join(dir,'.dependencies/ui');
fs.rmSync(target,{recursive:true,force:true});
fs.mkdirSync(target,{recursive:true});
const archive=execFileSync('git',['-C',source,'archive',pin,'packages/ui']);
execFileSync('tar',['-x','--strip-components=2','-C',target],{input:archive});
execFileSync('pnpm',['install','--ignore-workspace','--lockfile=false','--offline','--store-dir',path.join(root,'.pnpm-store')],{cwd:dir,stdio:'inherit'});
const require=createRequire(import.meta.url);
execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'--target','ES2022','--lib','ES2022,DOM','--module','NodeNext','--moduleResolution','NodeNext','--jsx','react-jsx','--strict','--skipLibCheck','--declaration','--rootDir',path.join(target,'src'),'--outDir',path.join(target,'dist'),path.join(target,'src/index.ts')],{cwd:dir,stdio:'inherit'});
fs.copyFileSync(path.join(target,'src/styles.css'),path.join(target,'dist/styles.css'));
// pnpm copies local file dependencies; update only our installed artifact after compilation.
const installed=fs.realpathSync(path.join(dir,'node_modules/@ikun/ui'));
if(!installed.startsWith(dir+path.sep))throw new Error('Dependency must stay inside this prototype');
fs.cpSync(path.join(target,'dist'),path.join(installed,'dist'),{recursive:true});
console.log(`Prepared @ikun/ui from ${pin} inside ${dir}`);
