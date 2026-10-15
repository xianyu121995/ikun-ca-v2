import {withAuth,requireIdentity} from '../../../../modules/auth/dist/src/server.js';
import {projectsAuth,ipc,requestId,failure,type Principal} from '../projects';
import {hunterCall} from '../hunter';

const uuid='[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const commandPattern=new RegExp('^/api/v1/commands/(cmd_'+uuid+')$');
const projectPattern=new RegExp('^prj_'+uuid+'$');
async function notFound(response:Response,id:string){
  if(response.ok)return false;
  const envelope=await response.clone().json();
  if(envelope?.request_id!==id||Object.keys(envelope).sort().join(',')!=='error,request_id'
    ||!envelope.error||Object.keys(envelope.error).sort().join(',')!=='code,message,retryable'
    ||typeof envelope.error.code!=='string'||typeof envelope.error.message!=='string'||typeof envelope.error.retryable!=='boolean')throw Error('INVALID_ERROR_ENVELOPE');
  return response.status===404&&envelope.error.code==='NOT_FOUND';
}
async function trackingCommand(command:string,id:string,signal:AbortSignal){
  const target=process.env.TRACKING_API_URL,token=process.env.TRACKING_API_TOKEN;
  if(!target||!token||token.length<32)return failure(id,503,'AUTH_NOT_CONFIGURED','Tracking 尚未接入，监控结果待核实');
  try{
    const url=new URL(target);
    if(url.protocol!=='http:'||!['127.0.0.1','[::1]'].includes(url.hostname)||url.pathname!=='/'||url.username||url.password||url.search||url.hash)throw Error('INVALID_DIRECTION');
    const response=await fetch(url.origin+'/internal/v1/commands/'+encodeURIComponent(command),{headers:{authorization:'Bearer '+token,'x-request-id':id},signal,cache:'no-store',redirect:'error'});
    const bytes=await response.arrayBuffer();if(bytes.byteLength>65536)throw Error('RESPONSE_LIMIT');
    const envelope=JSON.parse(new TextDecoder().decode(bytes));if(envelope?.request_id!==id||!('data'in envelope||'error'in envelope))throw Error('INVALID_ENVELOPE');
    return new Response(bytes,{status:response.status,headers:{'content-type':'application/json','cache-control':'no-store','x-request-id':id}});
  }catch{return failure(id,503,'UPSTREAM_UNAVAILABLE','Tracking 状态未能核实');}
}
async function projection(response:Response,command:string,id:string,project?:string){
  const envelope=await response.clone().json(),data=envelope?.data;
  const fields='command_id,error_code,project_id,request_id,revision,state,subscription_id,updated_at';
  if(!envelope||Object.keys(envelope).sort().join(',')!=='data,request_id'||envelope.request_id!==id
    ||!data||Array.isArray(data)||Object.keys(data).sort().join(',')!==fields
    ||data.command_id!==command||!['accepted','pending','running','succeeded','failed','unknown'].includes(data.state)
    ||data.project_id!==null&&(typeof data.project_id!=='string'||!projectPattern.test(data.project_id))
    ||project!==undefined&&data.project_id!==project
    ||data.subscription_id!==null&&(typeof data.subscription_id!=='string'||!new RegExp('^sub_'+uuid+'$').test(data.subscription_id))
    ||data.subscription_id!==null&&data.project_id===null
    ||data.revision!==null&&(!Number.isSafeInteger(data.revision)||data.revision<1)
    ||typeof data.updated_at!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(data.updated_at)
    ||!Number.isFinite(Date.parse(data.updated_at))||new Date(data.updated_at).toISOString().slice(0,19)!==data.updated_at.slice(0,19)
    ||data.error_code!==null&&(typeof data.error_code!=='string'||data.error_code.length>64)
    ||typeof data.request_id!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(data.request_id)||data.request_id!==id)throw Error('INVALID_COMMAND_PROJECTION');
  return data;
}
async function canonical(principal:Principal,command:string,id:string,signal:AbortSignal){
  return ipc({operation:'command',target:command,principal,request_id:id},signal);
}
type Lookups={projects:()=>Promise<Response>;hunter:()=>Promise<Response>;tracking:()=>Promise<Response>;canonical:(project:string)=>Promise<Response>};
function view(data:unknown,id:string){return Response.json({data,request_id:id},{headers:{'cache-control':'no-store','x-request-id':id}});}
/** Resolve ownership, without downgrading an unavailable authoritative source to NOT_FOUND. */
export async function resolveCommand(command:string,id:string,lookups:Lookups){
  const unavailable=()=>failure(id,503,'UPSTREAM_UNAVAILABLE','原命令结果待核实，请勿重复确认');
  const directView=async(response:Response)=>{
    const known=await projection(response,command,id);if(!known.project_id)throw Error('CANONICAL_REQUIRED');
    const result=await lookups.canonical(known.project_id);
    if(!result.ok){await notFound(result,id);return result.status===404?unavailable():result;}
    const envelope=await result.clone().json();
    if(envelope?.request_id!==id||envelope.data?.project_id!==known.project_id)throw Error('CANONICAL_MISMATCH');
    return view(known,id);
  };
  try{
    const local=await lookups.projects();
    if(local.ok){
      const known=await projection(local,command,id);if(!known.project_id)throw Error('CANONICAL_REQUIRED');
      const actual=await lookups.tracking();
      if(await notFound(actual,id))return ['pending','unknown'].includes(known.state)?view(known,id):unavailable();
      return actual.ok?view(await projection(actual,command,id,known.project_id),id):actual;
    }
    // Projects canonical is authoritative. An error here is never a licence to switch owner.
    if(!await notFound(local,id))return local;
    // Once Projects proves absence, these are independent original-ID ownership probes.
    // A valid direct Tracking command remains readable while the unrelated Hunter is down.
    const hunterProbe=lookups.hunter(),trackingProbe=lookups.tracking();
    const first=await Promise.race([hunterProbe.then(response=>({source:'hunter',response})),trackingProbe.then(response=>({source:'tracking',response}))]);
    if(first.response.ok){
      if(first.source==='tracking')return await directView(first.response);
      const owned=await projection(first.response,command,id);
      if(owned.project_id===null)return view(owned,id);
    }
    const [hunter,direct]=await Promise.all([hunterProbe,trackingProbe]);
    if(hunter.ok){
      const known=await projection(hunter,command,id);
      if(known.project_id===null&&!direct.ok)return view(known,id);
      const mapped=await lookups.projects();
      if(!mapped.ok){await notFound(mapped,id);return mapped.status===404?unavailable():mapped;}
      const project=await projection(mapped,command,id);if(!project.project_id)throw Error('CANONICAL_REQUIRED');
      if(known.project_id!==null&&known.project_id!==project.project_id)throw Error('CANONICAL_MISMATCH');
      if(await notFound(direct,id))return ['pending','unknown'].includes(project.state)?view(project,id):unavailable();
      return direct.ok?view(await projection(direct,command,id,project.project_id),id):direct;
    }
    if(direct.ok)return await directView(direct);
    const hunterMissing=await notFound(hunter,id),trackingMissing=await notFound(direct,id);
    if(hunterMissing&&trackingMissing)return local;
    return hunterMissing?direct:hunter;
  }catch{return unavailable();}
}
/** Original ID and existing domain projections only; GET never claims or sends outbox work. */
export function commandGateway(original:Request){
  projectsAuth();const id=requestId(original),headers=new Headers(original.headers);headers.set('x-request-id',id);
  const request=new Request(original.url,{method:original.method,headers,signal:original.signal});
  return withAuth(request,async()=>{
    const principal=requireIdentity(request),url=new URL(request.url),match=commandPattern.exec(url.pathname);
    if(!match||url.search)return failure(id,422,'VALIDATION_ERROR','命令标识或查询字段无效');
    const command=match[1]!,abort=new AbortController(),signal=AbortSignal.any([request.signal,abort.signal,AbortSignal.timeout(8000)]);
    try{return await resolveCommand(command,id,{
      projects:()=>canonical(principal,command,id,signal),
      hunter:()=>hunterCall('/internal/v1/commands/'+command,id,principal,'GET',undefined,{},signal),
      tracking:()=>trackingCommand(command,id,signal),
      canonical:project=>ipc({operation:'get',target:project,principal,request_id:id},signal),
    });}finally{abort.abort();}
  });
}
