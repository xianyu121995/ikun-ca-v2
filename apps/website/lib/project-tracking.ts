import {requireSuperadmin,withAuth} from '../../../modules/auth/dist/src/server.js';
import {ipc,requestId,failure} from './projects';
import {hunterCall} from './hunter';
import {trackingService,trackingRoute,readBody} from './tracking';
import {existingTracking,existingTrackingMessage,normalizeXHandle,type ExistingTracking} from './project-tracking-model';

type Project={project_id:string;name:string;revision:number};
export type ProjectTrackingPorts={
  project:()=>Promise<Response>;
  subscriptions:(cursor:string|null)=>Promise<Response>;
  discoveries:(state:'tracking'|'ignored',cursor:string|null)=>Promise<Response>;
  create:(body:Record<string,unknown>)=>Promise<Response>;
};
class Rejected {constructor(readonly response:Response){}}
async function data(response:Response) {
  if(!response.ok)throw new Rejected(response);
  const value=await response.json();if(!value?.data||typeof value.data!=='object')throw Error('INVALID_RESPONSE');return value.data;
}
async function pages<T>(read:(cursor:string|null)=>Promise<Response>):Promise<T[]> {
  const rows:T[]=[],seen=new Set<string>();let cursor:string|null=null;
  do {
    const page=await data(await read(cursor));if(!Array.isArray(page.items))throw Error('INVALID_PAGE');
    rows.push(...page.items);cursor=page.next_cursor??null;
    if(cursor){if(typeof cursor!=='string'||seen.has(cursor)||seen.size>=100)throw Error('INVALID_CURSOR');seen.add(cursor);}
  }while(cursor);return rows;
}
/** Cross-domain composition uses only the existing private APIs; no direct database access. */
export function projectTrackingRoute(request:Request,overrides?:ProjectTrackingPorts) {
  return withAuth(request,async()=>{
    const principal=requireSuperadmin(request),id=requestId(request),url=new URL(request.url);
    const projectId=url.searchParams.get('project_id');
    if(!['GET','POST'].includes(request.method)||url.searchParams.size!==1||url.searchParams.getAll('project_id').length!==1||!/^prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(projectId??''))
      return failure(id,422,'VALIDATION_ERROR','需要有效项目 ID');
    const ports:ProjectTrackingPorts=overrides??{
      project:()=>ipc({operation:'get',target:projectId!,principal,request_id:id},request.signal),
      subscriptions:cursor=>trackingService('subscriptions?limit=100'+(cursor?'&cursor='+encodeURIComponent(cursor):''),id,{signal:request.signal}),
      discoveries:(state,cursor)=>hunterCall('/api/v1/hunter/signals?limit=100&review_state='+state+(cursor?'&cursor='+encodeURIComponent(cursor):''),id,principal,'GET',undefined,{},request.signal),
      create:body=>{const headers=new Headers(request.headers);headers.delete('content-length');return trackingRoute(new Request(new URL('/api/v1/tracking/subscriptions',request.url),{method:'POST',headers,body:JSON.stringify(body),signal:request.signal}));},
    };
    try {
      let supplied:string|null=null;
      if(request.method==='POST') {
        if(!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(request.headers.get('idempotency-key')??''))return failure(id,422,'VALIDATION_ERROR','需要有效幂等键');
        let body;try{body=await readBody(request);}catch{return failure(id,422,'VALIDATION_ERROR','请求内容无效');}
        if(Object.keys(body).some(k=>k!=='x_handle')||('x_handle'in body&&!normalizeXHandle(body.x_handle)))return failure(id,422,'VALIDATION_ERROR','X 用户名只能包含 1–15 位字母、数字和下划线');
        supplied=normalizeXHandle(body.x_handle);
      }
      const subscriptions=async()=>{
        const items=await pages<ExistingTracking>(ports.subscriptions);
        if(items.some(row=>!row||typeof row.project_id!=='string'||typeof row.subscription_id!=='string'||!normalizeXHandle(row.x_handle)||!['running','stopped','removed'].includes(row.desired_state)))throw Error('INVALID_SUBSCRIPTION');
        return items;
      };
      const [project,rows]=await Promise.all([ports.project().then(data) as Promise<Project>,subscriptions()]);
      if(project.project_id!==projectId||!Number.isSafeInteger(project.revision)||project.revision<1||typeof project.name!=='string')throw Error('INVALID_PROJECT');
      const reply=(status:'ready'|'already'|'added',message:string,extra:Record<string,unknown>={})=>Response.json({data:{status,message,project_revision:project.revision,...extra},request_id:id},{headers:{'cache-control':'no-store'}});
      const duplicate=(row:ExistingTracking)=>reply('already',existingTrackingMessage(row));
      const byProject=existingTracking(rows,projectId!,null);if(byProject)return duplicate(byProject);
      if(request.method==='POST'&&request.headers.get('if-match')!==`"rev-${project.revision}"`)return failure(id,409,'VERSION_CONFLICT','项目资料已更新，请重新点击加入追踪');
      let source:{x_handle?:unknown;x_user_id?:unknown}|undefined,warning='';
      try {
        for(const state of ['tracking','ignored'] as const) {
          const discoveries=await pages<{project_id:string;x_handle:unknown;x_user_id?:unknown}>(cursor=>ports.discoveries(state,cursor));
          const matches=discoveries.filter(row=>row.project_id===projectId&&normalizeXHandle(row.x_handle));
          if(new Set(matches.map(row=>normalizeXHandle(row.x_handle))).size>1){warning='项目关联多个 X 账号，请手动确认';break;}
          source=matches[0];if(source)break;
        }
      }catch{warning='猎手来源暂不可用，请手动确认 X 账号';}
      const automatic=normalizeXHandle(source?.x_handle),handle=automatic??supplied;
      if(request.method==='POST'&&automatic&&supplied&&automatic!==supplied)return failure(id,409,'CONFLICT','猎手记录的 X 账号已更新，请重新核对');
      const match=existingTracking(rows,projectId!,handle);if(match)return duplicate(match);
      if(request.method==='GET')return reply('ready','', {x_handle:automatic,warning});
      if(!handle)return failure(id,422,'VALIDATION_ERROR','请填写 X 用户名');
      const created=await ports.create({project_id:projectId,name:project.name,x_handle:handle,x_user_id:automatic&&typeof source?.x_user_id==='string'?source.x_user_id:null,notes:'',confirmed:true});
      if(created.status===409) {
        const fresh=existingTracking(await subscriptions(),projectId!,handle);if(fresh)return duplicate(fresh);
      }
      const result=await data(created);
      if(!result.subscription_id||!['accepted','pending','running','succeeded'].includes(result.state))return failure(id,409,'CONFLICT',result.error_code||'追踪未成功，请查看追踪页');
      return reply('added','已加入追踪',{x_handle:handle});
    }catch(error){return error instanceof Rejected?error.response:failure(id,503,'UPSTREAM_UNAVAILABLE','追踪来源暂不可用，请稍后重试');}
  });
}
