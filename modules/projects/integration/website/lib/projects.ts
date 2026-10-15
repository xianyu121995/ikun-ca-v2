import {randomUUID,timingSafeEqual} from 'node:crypto';
import {lstat} from 'node:fs/promises';
import http from 'node:http';
import {auth,requireIdentity,requireSuperadmin,withAuth} from '../../../modules/auth/dist/src/server.js';
import type {AuthHttp} from '../../../modules/auth/dist/src/http.js';

const uuid='[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const readPaths=[/^\/api\/v1\/projects\/(?:home-summary|milestones)$/,new RegExp('^/api/v1/projects/operations/'+uuid+'$')];
const globalState=globalThis as typeof globalThis & {ikunAuth?:AuthHttp;ikunProjectsPolicy?:boolean};
/** Reviewed additive route admission on the very same B1 store/singleton. */
export function projectsAuth(){
  const current=auth();
  if(!globalState.ikunProjectsPolicy){const CurrentAuth=current.constructor as typeof AuthHttp;globalState.ikunAuth=new CurrentAuth(current.store,[...current.readApi,...readPaths],current.readPages);globalState.ikunProjectsPolicy=true;}
  return auth();
}
export function requestId(request:Request){const id=request.headers.get('x-request-id');return id&&/^[A-Za-z0-9_-]{1,64}$/.test(id)?id:randomUUID();}
export function failure(id:string,status:number,code:string,message:string){return Response.json({error:{code,message,retryable:[429,502,503,504].includes(status)},request_id:id},{status,headers:{'cache-control':'no-store','x-request-id':id}});}
export type Principal={user_id:string;tenant_id:'ikun-main';role:'superadmin'|'user'};
export type Rpc={operation:string;request_id:string;principal?:Principal;source?:'hunter'|'tracking';target?:string;query?:Record<string,string>;body?:unknown;idempotency_key?:string|null;if_match?:string|null;contract?:string};
export async function ipc(payload:Rpc,signal?:AbortSignal):Promise<Response>{
  const socketPath=process.env.IKUN_PROJECTS_IPC_SOCKET,token=process.env.IKUN_PROJECTS_IPC_TOKEN,build=process.env.IKUN_PROJECTS_BUILD_SHA;
  if(!socketPath||!socketPath.startsWith('/')||Buffer.byteLength(socketPath)>100||!token||token.length<32||!build||!/^[a-f0-9]{40}$/.test(build))return failure(payload.request_id,503,'DB_UNAVAILABLE','项目 IPC 未就绪');
  try{
    const [socket,parent]=await Promise.all([lstat(socketPath),lstat(socketPath.slice(0,socketPath.lastIndexOf('/')))]);
    if(!socket.isSocket()||socket.uid!==process.getuid?.()||(socket.mode&0o777)!==0o600||!parent.isDirectory()||parent.uid!==socket.uid||(parent.mode&0o777)!==0o700)throw Error('UNSAFE_IPC');
    const data=Buffer.from(JSON.stringify(payload));
    if(data.length>131072)return failure(payload.request_id,413,'VALIDATION_ERROR','请求过大');
    return await new Promise<Response>((resolve,reject)=>{
      const timer=setTimeout(()=>req.destroy(Error('IPC_TIMEOUT')),8000);
      const req=http.request({socketPath,path:'/v1/rpc',method:'POST',signal,headers:{authorization:'Bearer '+token,'x-ikun-build-sha':build,'content-type':'application/json','content-length':data.length,'x-request-id':payload.request_id}},res=>{
        const pieces:Buffer[]=[];let size=0;
        res.on('data',(chunk:Buffer)=>{size+=chunk.length;if(size>4194304)req.destroy(Error('IPC_BODY_TOO_LARGE'));else pieces.push(chunk);});
        res.on('end',()=>{clearTimeout(timer);try{const body=Buffer.concat(pieces);const envelope=JSON.parse(body.toString());if(!envelope||envelope.request_id!==payload.request_id||(!('data'in envelope)&&!('error'in envelope)))throw Error('IPC_ENVELOPE');resolve(new Response(body,{status:res.statusCode??502,headers:{'content-type':'application/json','cache-control':'no-store','x-request-id':payload.request_id,...(res.headers.etag?{etag:res.headers.etag}:{})}}));}catch(error){reject(error);}});
        res.on('error',reject);
      });
      req.on('error',error=>{clearTimeout(timer);reject(error);});req.end(data);
    });
  }catch{return failure(payload.request_id,503,'DB_UNAVAILABLE','项目操作结果待核对，请查询原操作回执');}
}
async function boundedJson(request:Request,allowEmpty=false){
  const reader=request.body?.getReader();if(!reader){if(allowEmpty)return {};throw Error('INVALID_BODY');}
  let size=0;const pieces:Uint8Array[]=[];const deadline=Date.now()+5000;
  try{while(true){let timer:ReturnType<typeof setTimeout>|undefined;const part=await Promise.race([reader.read(),new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Error('BODY_TIMEOUT')),Math.max(1,deadline-Date.now()));})]).finally(()=>clearTimeout(timer));if(part.done)break;size+=part.value.length;if(size>65536)throw Error('BODY_TOO_LARGE');pieces.push(part.value);}if(size===0&&allowEmpty)return {};const parsed=JSON.parse(Buffer.concat(pieces).toString());if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw Error('INVALID_BODY');return parsed;}catch(error){void reader.cancel().catch(()=>{});throw error;}finally{reader.releaseLock();}
}
export async function projectsRoute(original:Request){
  projectsAuth();const id=requestId(original);const headers=new Headers(original.headers);headers.set('x-request-id',id);const request=new Request(original,{headers});
  return withAuth(request,async()=>{
    const method=request.method;const principal=['GET','HEAD'].includes(method)?requireIdentity(request):requireSuperadmin(request);
    const url=new URL(request.url);const query:Record<string,string>={};for(const key of url.searchParams.keys()){if(url.searchParams.getAll(key).length!==1)return failure(id,422,'VALIDATION_ERROR','不接受重复查询字段');query[key]=url.searchParams.get(key)!;}
    const view=query.view;delete query.view;if(view!==undefined&&view!=='home-v1')return failure(id,422,'VALIDATION_ERROR','未知项目投影');
    const contract=view==='home-v1'?'projects-home-v1':'phase2-v1.0.0';const root='/api/v1/projects';const suffix=url.pathname.slice(root.length);
    let operation:string|undefined,target:string|undefined;
    if(url.pathname.startsWith('/api/v1/commands/')){operation=method==='GET'?'command':undefined;target=url.pathname.split('/').at(-1);}
    else if(suffix==='')operation=method==='GET'?'list':method==='POST'?'create':undefined;
    else if(suffix==='/home-summary')operation=method==='GET'?'summary':undefined;
    else if(suffix==='/milestones')operation=method==='GET'?'milestones':undefined;
    else if(suffix==='/completions')operation=method==='POST'?'completions':undefined;
    else if(new RegExp('^/operations/'+uuid+'$').test(suffix)){operation=method==='GET'?'reconcile':undefined;target=suffix.split('/').at(-1);}
    else{const match=new RegExp('^/(prj_'+uuid+')(?:/(home-membership|completion|restore))?$').exec(suffix);if(match){target=match[1];operation=match[2]?(method==='POST'?{'home-membership':'membership',completion:'completion',restore:'restore'}[match[2]]:undefined):({GET:'get',PATCH:'patch',DELETE:'delete'} as Record<string,string>)[method];}}
    if(!operation)return failure(id,404,'NOT_FOUND','项目路径或方法不受支持');
    if(operation!=='list'&&operation!=='summary'&&operation!=='milestones'&&operation!=='reconcile'&&Object.keys(query).length)return failure(id,422,'VALIDATION_ERROR','不支持查询字段');
    let body={};if(!['GET','HEAD','DELETE'].includes(method)){try{body=await boundedJson(request);}catch{return failure(id,422,'VALIDATION_ERROR','请求 JSON 无效或超出限制');}}
    if(method==='DELETE'&&request.body){try{if(Object.keys(await boundedJson(request,true)).length)throw Error();}catch{return failure(id,422,'VALIDATION_ERROR','DELETE 不接受资料');}}
    return ipc({operation,principal,request_id:id,target,query,body,contract,idempotency_key:request.headers.get('idempotency-key'),if_match:request.headers.get('if-match')},request.signal);
  });
}
/** Direction credential binds Hunter only; user sessions cannot invoke this entry. */
export async function ingestRoute(request:Request){
  const id=requestId(request);const path=new URL(request.url).pathname;
  const source=path.split('/')[4];
  const expected=source==='hunter'?process.env.PROJECTS_INGEST_HUNTER_TOKEN:source==='tracking'?process.env.PROJECTS_INGEST_TRACKING_TOKEN:undefined;const given=request.headers.get('authorization')??'';
  if(!expected||expected.length<32||Buffer.byteLength(given)!==Buffer.byteLength('Bearer '+expected)||!timingSafeEqual(Buffer.from(given),Buffer.from('Bearer '+expected)))return failure(id,401,'UNAUTHENTICATED','来源凭据无效');
  const receipt=new RegExp('^/internal/v1/receipts/(hunter|tracking)/(evt_'+uuid+')$').exec(path);
  if(request.method==='GET'&&receipt)return ipc({operation:'receipt',source:receipt[1] as 'hunter'|'tracking',target:receipt[2],request_id:id},request.signal);
  if(request.method!=='POST'||!/^\/internal\/v1\/ingest\/(hunter|tracking)$/.test(path))return failure(id,404,'NOT_FOUND','来源入口不存在');
  if(source!=='hunter')return failure(id,501,'NOT_IMPLEMENTED','本候选仅接收人工确认的 Hunter 项目资料');
  if(request.headers.get('content-type')?.split(';')[0]?.toLowerCase()!=='application/json')return failure(id,415,'VALIDATION_ERROR','请使用 application/json');
  try{return ipc({operation:'ingest',source:'hunter',request_id:id,body:await boundedJson(request)},request.signal);}catch{return failure(id,422,'VALIDATION_ERROR','事件 JSON 无效');}
}
