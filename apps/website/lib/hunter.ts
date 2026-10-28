import {randomUUID} from 'node:crypto';
import {auth,requireIdentity,requireSuperadmin,withAuth} from '../../../modules/auth/dist/src/server.js';
import {shutdownSignal} from './shutdown';

type Principal={user_id:string;tenant_id:'ikun-main';role:'superadmin'|'user'};
const id=(request:Request)=>{const value=request.headers.get('x-request-id');return value&&/^[A-Za-z0-9_-]{1,64}$/.test(value)?value:randomUUID();};
function authenticatedRequest(original:Request,requestId:string){
  const headers=new Headers(original.headers);headers.set('x-request-id',requestId);
  const init:RequestInit&{duplex?:'half'}={method:original.method,headers,signal:original.signal};
  if(!['GET','HEAD'].includes(original.method)&&original.body){init.body=original.body;init.duplex='half';}
  // Next's Request object may come from another fetch implementation/realm.
  return new Request(original.url,init);
}
function fail(requestId:string,status:number,code:string,message:string){return Response.json({error:{code,message,retryable:code!=='AUTH_NOT_CONFIGURED'&&[429,502,503,504].includes(status)},request_id:requestId},{status,headers:{'x-request-id':requestId,'cache-control':'no-store'}});}
function settings(){
  const token=process.env.HUNTER_API_TOKEN,origin=new URL(process.env.IKUN_HUNTER_ORIGIN??'http://127.0.0.1:3311');
  if(!token||token.length<32||origin.protocol!=='http:'||!['127.0.0.1','[::1]','localhost'].includes(origin.hostname)||origin.pathname!=='/'||origin.username||origin.password||origin.search||origin.hash)throw Error('HUNTER_NOT_CONFIGURED');
  return {token,origin};
}
async function bounded(request:Request){
  const reader=request.body?.getReader();if(!reader)return {};
  const chunks:Uint8Array[]=[];let size=0;const end=Date.now()+5000;
  try{while(true){let timer:ReturnType<typeof setTimeout>|undefined;const next=await Promise.race([reader.read(),new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Error('BODY_TIMEOUT')),Math.max(1,end-Date.now()));})]).finally(()=>clearTimeout(timer));if(next.done)break;size+=next.value.length;if(size>65536)throw Error('BODY_TOO_LARGE');chunks.push(next.value);}const text=Buffer.concat(chunks).toString();const data=text?JSON.parse(text):{};if(!data||typeof data!=='object'||Array.isArray(data))throw Error('INVALID_BODY');return text||'{}';}catch(error){void reader.cancel().catch(()=>{});throw error;}finally{reader.releaseLock();}
}
export async function hunterCall(path:string,requestId:string,principal:Principal,method='GET',body?:unknown,extra:Record<string,string>={},signal?:AbortSignal){
  let configured:ReturnType<typeof settings>;
  try{configured=settings();}catch{return fail(requestId,503,'AUTH_NOT_CONFIGURED','Hunter 方向配置未就绪。');}
  try{
    const {token,origin}=configured;
    if(!path.startsWith('/api/v1/hunter/')&&!/^\/internal\/v1\/(?:commands\/cmd_[a-f0-9-]{36}|events(?:\?|$))/.test(path))throw Error('INVALID_TARGET');
    const response=await fetch(new URL(path,origin),{method,headers:{authorization:'Bearer '+token,'x-ikun-principal':JSON.stringify(principal),'content-type':'application/json','x-request-id':requestId,...extra},body:body===undefined?undefined:typeof body==='string'?body:JSON.stringify(body),cache:'no-store',redirect:'error',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(8000)]):AbortSignal.timeout(8000)});
    const text=await response.text();if(text.length>4194304)throw Error('RESPONSE_TOO_LARGE');const data=JSON.parse(text);
    if(data?.request_id!==requestId||(!('data' in data)&&!('error' in data)))throw Error('INVALID_ENVELOPE');
    const headers:Record<string,string>={'content-type':'application/json','cache-control':'no-store','x-request-id':requestId};const etag=response.headers.get('etag');if(etag)headers.etag=etag;
    return new Response(text,{status:response.status,headers});
  }catch{return fail(requestId,502,'UPSTREAM_UNAVAILABLE','Hunter 暂不可用；写入结果须核对原命令，不要重复提交。');}
}
/** Called inside the real Route Handler. Never forwards browser identity headers. */
export async function hunterRoute(original:Request){
  const requestId=id(original),request=authenticatedRequest(original,requestId);
  return withAuth(request,async()=>{
    const principal=['GET','HEAD'].includes(request.method)?requireIdentity(request):requireSuperadmin(request);
    const path=new URL(request.url).pathname;
    if(!/^\/api\/v1\/hunter\/(?:signals|accounts(?:\/[A-Za-z0-9_-]+)?|discoveries\/[A-Za-z0-9_-]+(?:\/monitoring-requests)?)$/.test(path))return fail(requestId,404,'NOT_FOUND','Hunter 入口不存在');
    if(path.includes('/accounts')&&principal.role!=='superadmin')return fail(requestId,403,'FORBIDDEN','猎手管理仅限超级管理员');
    let body:unknown;
    if(!['GET','HEAD'].includes(request.method)){try{body=await bounded(request);}catch{return fail(requestId,422,'VALIDATION_ERROR','请求 JSON 无效或超出限制');}}
    const outgoing:Record<string,string>={};for(const key of ['idempotency-key','if-match']){const value=request.headers.get(key);if(value!==null)outgoing[key]=value;}
    return hunterCall(path+new URL(request.url).search,requestId,principal,request.method,body,outgoing,request.signal);
  });
}
/** Optional ownership-aware command gateway hook; final Projects composition belongs to C0. */
export async function hunterCommandRoute(request:Request,commandId:string){
  return withAuth(request,async()=>hunterCall('/internal/v1/commands/'+commandId,id(request),requireIdentity(request),'GET',undefined,{},request.signal));
}
/** SSE contribution candidate. The website owns final multi-source cursor composition. */
export async function hunterEventsRoute(original:Request){
  const requestId=id(original),request=authenticatedRequest(original,requestId);
  return withAuth(request,async()=>{
    requireIdentity(request);
    const liveIdentity=():Principal=>{const actor=auth().authorize(request,false);if(actor.tenant_id!=='ikun-main')throw Error('INVALID_SCOPE');return {user_id:actor.id,tenant_id:actor.tenant_id,role:actor.role};};
    const resume=request.headers.get('last-event-id');if(resume&&!/^hunter:[0-9]{1,15}$/.test(resume))return fail(requestId,422,'VALIDATION_ERROR','Hunter 事件游标无效');
    let after=resume?Number(resume.slice(7)):0,done=false,timer:ReturnType<typeof setTimeout>|undefined,wake:(()=>void)|undefined;
    const controller=new AbortController(),encoder=new TextEncoder();let heartbeat=Date.now();
    let output:ReadableStreamDefaultController<Uint8Array>|undefined;
    const release=()=>shutdownSignal().removeEventListener('abort',shutdown);
    function shutdown(){release();if(done)return;done=true;controller.abort();clearTimeout(timer);wake?.();try{output?.close();}catch{}}
    const body=new ReadableStream<Uint8Array>({start(stream){output=stream;if(shutdownSignal().aborted)shutdown();else shutdownSignal().addEventListener('abort',shutdown,{once:true});},async pull(stream){
      try{
        while(!done){
          const principal=liveIdentity();
          const result=await hunterCall('/internal/v1/events?after='+after,requestId,principal,'GET',undefined,{},controller.signal);
          if(!result.ok){done=true;release();stream.close();return;}
          const envelope=await result.json();const frames=envelope.data.items;
          if(!Array.isArray(frames))throw Error('INVALID_EVENTS');
          if(frames.length){
            let text='';for(const frame of frames){
              liveIdentity();
              if(!Number.isSafeInteger(frame.sequence)||frame.sequence<=after||!['hunter.discovery.updated','command.updated'].includes(frame.type))throw Error('INVALID_EVENT');
              after=frame.sequence;text+='id: hunter:'+after+'\nevent: '+frame.type+'\ndata: '+JSON.stringify({data:frame.data,request_id:requestId})+'\n\n';
            }
            stream.enqueue(encoder.encode(text));return;
          }
          if(Date.now()-heartbeat>=15000){liveIdentity();heartbeat=Date.now();stream.enqueue(encoder.encode(': heartbeat\n\n'));return;}
          await new Promise<void>(resolve=>{wake=resolve;timer=setTimeout(resolve,500);});
        }
      }catch{release();if(!done){done=true;controller.abort();stream.close();}}
    },cancel(){done=true;release();controller.abort();clearTimeout(timer);wake?.();}});
    return new Response(body,{headers:{'content-type':'text/event-stream','cache-control':'no-store','x-request-id':requestId,'x-accel-buffering':'no'}});
  });
}
