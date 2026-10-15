// Loopback static preview. No website service, business API, worker or database.
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import http from 'node:http';
const require=createRequire(import.meta.url),dir=path.dirname(fileURLToPath(import.meta.url));
const esbuild=require(require.resolve('esbuild',{paths:[path.dirname(require.resolve('tsx/package.json'))]}));
const output=path.join(dir,'.preview'),port=Number(process.env.HUNTER_V3_PORT||3803);
if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('Invalid port');
await fs.mkdir(output,{recursive:true});
await esbuild.build({entryPoints:[path.join(dir,'entry.tsx')],bundle:true,outfile:path.join(output,'app.js'),format:'esm',platform:'browser',jsx:'automatic',sourcemap:false,minify:false,define:{'process.env.NODE_ENV':'"development"'}});
const html='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ikun.ca · 项目发现 V3 · 独立演示</title><link rel="icon" href="data:,"><link rel="stylesheet" href="/app.css"></head><body style="margin:0;background:#071018"><div id="hunter-v3-root"></div><script type="module" src="/app.js"></script></body></html>';
const routes={'/app.js':[path.join(output,'app.js'),'text/javascript'],'/app.css':[path.join(output,'app.css'),'text/css'],'/reference':[path.join(dir,'reference/v3.html'),'text/html']};
const server=http.createServer(async(req,res)=>{res.setHeader('Cache-Control','no-store');res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'");if(req.method!=='GET'){res.writeHead(405);res.end('Static UI preview only');return;}const pathname=new URL(req.url||'/','http://127.0.0.1').pathname;if(pathname==='/'||pathname==='/prototypes/hunter-v3'){res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end(html);return;}if(pathname==='/favicon.ico'){res.writeHead(204);res.end();return;}const asset=routes[pathname];if(!asset){res.writeHead(404);res.end('Not found');return;}try{res.writeHead(200,{'Content-Type':`${asset[1]}; charset=utf-8`});res.end(await fs.readFile(asset[0]));}catch{res.writeHead(404);res.end('Missing asset');}});
server.listen(port,'127.0.0.1',()=>console.log(`V3 UI-only preview: http://127.0.0.1:${port}/prototypes/hunter-v3`));
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{server.close(()=>process.exit(0));server.closeAllConnections();});
