// Isolated UI QA only. Consume the one public package; never vendor its source.
import {execFileSync} from 'node:child_process';
import {cpSync,existsSync,mkdirSync,readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dirname,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const module=dirname(fileURLToPath(import.meta.url));
const root=resolve(module,'../../../..');
const pin=JSON.parse(readFileSync(join(module,'shared-ui-pin.json'),'utf8'));
const source=resolve(process.argv[2]||join(root,'../website/packages/ui'));
const sourceRoot=execFileSync('git',['rev-parse','--show-toplevel'],{cwd:source}).toString().trim();
const git=(...args)=>execFileSync('git',args,{cwd:sourceRoot});
const sha=value=>createHash('sha256').update(value).digest('hex');
const packagePrefix=relative(sourceRoot,source);
const sourceHead=git('rev-parse','HEAD').toString().trim();
if(sourceHead!==pin.commit)throw Error(`Expected public UI commit ${pin.commit}; got ${sourceHead}`);
if(git('status','--porcelain','--',packagePrefix).length)throw Error('Public UI package must be clean');
// Check every tracked package input against its pinned Git blob before compiling.
const tracked=git('ls-tree','-r','--name-only',pin.commit,'--',packagePrefix).toString().trim().split('\n');
for(const path of tracked)if(!readFileSync(join(sourceRoot,path)).equals(git('show',`${pin.commit}:${path}`)))throw Error(`Unpinned public input: ${path}`);
const destination=join(module,'node_modules/@ikun/ui');
mkdirSync(destination,{recursive:true});
const compiler=join(root,'node_modules/typescript/bin/tsc');
if(!existsSync(compiler))throw Error('Run the existing frozen workspace install first');
// Read public sources in place, emitting only an ignored dependency inside our UI directory.
execFileSync(process.execPath,[compiler,'-p',join(source,'tsconfig.json'),'--outDir',join(destination,'dist')],{cwd:module,stdio:'inherit'});
cpSync(join(source,'src/styles.css'),join(destination,'dist/styles.css'));
const metadata=JSON.parse(readFileSync(join(source,'package.json'),'utf8'));
writeFileSync(join(destination,'package.json'),JSON.stringify({name:metadata.name,version:metadata.version,type:metadata.type,sideEffects:metadata.sideEffects,exports:metadata.exports,peerDependencies:metadata.peerDependencies},null,2)+'\n');
const artifacts=Object.fromEntries(readdirSync(join(destination,'dist')).sort().map(name=>[name,sha(readFileSync(join(destination,'dist',name)))]));
const receipt={package:metadata.name,commit:pin.commit,source_clean:true,source_files_checked:tracked.length,artifacts};
writeFileSync(join(destination,'homepage-qa-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
process.stdout.write(JSON.stringify({package:metadata.name,commit:pin.commit,source_files_checked:tracked.length,scope:'ignored homepage-local dependency; root install unchanged'})+'\n');
