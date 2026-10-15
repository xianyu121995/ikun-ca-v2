// Static React UI preview only; does not start the website, worker, APIs or databases.
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import http from 'node:http';

const require=createRequire(import.meta.url);
const esbuild=require(require.resolve('esbuild',{paths:[path.dirname(require.resolve('tsx/package.json'))]}));
const dir=path.dirname(fileURLToPath(import.meta.url));
const output=path.resolve(dir,'../../prototypes/hunter-discovery/.ui0-preview');
const port=Number(process.env.HUNTER_UI_PREVIEW_PORT||3800);
if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('Invalid preview port');
await fs.mkdir(output,{recursive:true});
await esbuild.build({entryPoints:[path.join(dir,'browser-entry.tsx')],bundle:true,outfile:path.join(output,'app.js'),format:'esm',platform:'browser',jsx:'automatic',sourcemap:false,minify:false,define:{'process.env.NODE_ENV':'"development"'}});
const html='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>HunterRadar · UI0 隔离原型</title><link rel="icon" href="data:,"><link rel="stylesheet" href="/app.css"></head><body style="margin:0;background:#0b0e12"><div id="hunter-ui-root"></div><script type="module" src="/app.js"></script></body></html>';
const files={'/app.js':['app.js','text/javascript; charset=utf-8'],'/app.css':['app.css','text/css; charset=utf-8']};
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url||'/','http://127.0.0.1');res.setHeader('Cache-Control','no-store');
  if(req.method!=='GET'){res.writeHead(405);res.end('Static preview only');return;}
  if(url.pathname==='/'||url.pathname==='/prototypes/hunter'){res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end(html);return;}
  const asset=files[url.pathname];if(!asset){res.writeHead(404);res.end('Not found');return;}
  try{const bytes=await fs.readFile(path.join(output,asset[0]));res.writeHead(200,{'Content-Type':asset[1]});res.end(bytes);}catch{res.writeHead(404);res.end('Asset unavailable');}
});
server.listen(port,'127.0.0.1',()=>console.log(`UI-only preview: http://127.0.0.1:${port}/prototypes/hunter`));
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{server.close(()=>process.exit(0));server.closeAllConnections();});
