import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {withAuth,requireIdentity} from '../../../../../../../modules/auth/dist/src/server.js';
export const dynamic='force-dynamic';
export async function GET(request:Request){return withAuth(request,async()=>{requireIdentity(request);let data:{checked_at:number;healthy:boolean;errors:string[]};try{if(!process.env.DATA_ROOT)throw Error();data=JSON.parse(await readFile(resolve(process.env.DATA_ROOT,'../ops/health.json'),'utf8'));if(Date.now()/1000-data.checked_at>660) data={...data,healthy:false,errors:['健康检查已超过 10 分钟未更新']};}catch{data={checked_at:0,healthy:false,errors:['健康检查尚未就绪']};}return Response.json({data},{headers:{'cache-control':'no-store'}});});}
