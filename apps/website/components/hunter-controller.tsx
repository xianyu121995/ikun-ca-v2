'use client';
import {useEffect,useRef,useState} from 'react';
import App from '../features/hunter-discovery/v3/App';
import type {Project,Grade,Filters} from '../features/hunter-discovery/v3/model';
import type {DiscoveryDTO,CommandResult,HunterAccountDTO,ProjectFields} from '../features/hunter-discovery/model';
import './hunter-host.css';
import {clearClientSession,invalidateClientData,peekClientData,readClientData,saveClientData} from '../lib/client-session-cache';
import {loadTrackingSubscriptions,invalidateTrackingSubscriptions} from '../lib/tracking-subscriptions-cache';

type Session={user_id:string;role:'superadmin'|'user';csrf_token:string;must_change_password:boolean;capabilities:{can_manage_hunter:boolean}};
type Snapshot={records:DiscoveryDTO[];nextCursor:string|null;cursor:string|null;history:(string|null)[];query:Record<string,string>;filterValues:Filters;counts:{total:number;enabled:number}|null};
type PublicError={code:string;message:string};
type Outcome={ok:true;message:string;project?:Project}|{ok:false;error:PublicError};
const toProject=(row:DiscoveryDTO):Project=>({id:row.discovery_id,name:row.project.name,handle:row.x_handle,bio:row.profile_bio,hunters:row.signal_count,grade:row.project.rating as Grade,
 status:row.monitoring_state==='succeeded'?'joined':row.review_state==='reviewed'?'reviewed':'pending',foundAt:row.discovered_at?Date.parse(row.discovered_at):NaN,website:row.project.website_url||'',description:row.project.description,category:row.project.category||'',notes:row.project.notes,watch:row.monitoring_state==='succeeded',monitoringMessage:(row as DiscoveryDTO & {monitoring_message?:string}).monitoring_message,ai:(row as DiscoveryDTO & {ai_suggestion?:Project['ai']}).ai_suggestion??null});
export interface LiveBinding{
 initialFilters?:Filters;
 projects:Project[];role:'superadmin'|'user';loading:boolean;refreshing:boolean;error:string|null;
 fixture:boolean;nextCursor:string|null;previous:boolean;blockedIds:ReadonlySet<string>;
 counts:{total:number;enabled:number}|null;
 confirm:(project:Project)=>Promise<Outcome>;ignore:(project:Project)=>Promise<Outcome>;addHome:(project:Project)=>Promise<Outcome>;save:(project:Project)=>Promise<Outcome>;manage:(action:'add'|'enable'|'disable'|'remove',handle:string)=>Promise<Outcome>;
 refresh:()=>void;next:()=>void;back:()=>void;
 filter:(key:string,value:string)=>void;
}
class ApiError extends Error{constructor(readonly code:string,message:string){super(message)}}
const BUSY_MESSAGE='服务繁忙，请稍后重试';
// Proxies (e.g. Cloudflare 502/524) can answer with an HTML page; never feed that to JSON.parse.
async function readApiBody(response:Response):Promise<{data?:unknown;error?:{code?:string;message?:string}}|null>{
 if(!/json/i.test(response.headers.get('content-type')||''))return null;
 try{const value=await response.json();return value&&typeof value==='object'?value:null;}catch{return null;}
}
export default function HunterController({session,fixture=false}:{session:Session;fixture?:boolean}){
 const scope=session.user_id,snapshot=useRef(peekClientData<Snapshot>(scope,'hunter:view')).current;
 const [records,setRecords]=useState<DiscoveryDTO[]>(snapshot?.records??[]),[loading,setLoading]=useState(!snapshot),[refreshing,setRefreshing]=useState(false),[error,setError]=useState<string|null>(null);
 const [nextCursor,setNextCursor]=useState<string|null>(snapshot?.nextCursor??null),[cursor,setCursor]=useState<string|null>(snapshot?.cursor??null),[history,setHistory]=useState<(string|null)[]>(snapshot?.history??[]),[counts,setCounts]=useState<{total:number;enabled:number}|null>(snapshot?.counts??null);
 const [blockedIds,setBlockedIds]=useState<ReadonlySet<string>>(new Set()),pending=useRef(new Set<string>()),operations=useRef(new Map<string,{key:string;body:string}>());
 const [query,setQuery]=useState<Record<string,string>>(snapshot?.query??{}),[revoked,setRevoked]=useState(false);
 const [filterValues,setFilterValues]=useState<Filters>(snapshot?.filterValues??{query:'',time:'all',grade:'all',status:'all'});
 const researchOps=useRef(new Map<string,{key:string;body:string;revision:number}>());
 const [researchUnknown,setResearchUnknown]=useState<ReadonlySet<string>>(new Set());
 const generation=useRef(0),active=useRef<AbortController|null>(null),readAt=useRef(Date.now()),currentRecords=useRef(records);currentRecords.current=records;
 async function api(path:string,method='GET',body?:unknown,extra:Record<string,string>={},signal?:AbortSignal){
  const response=await fetch(path,{method,headers:{'content-type':'application/json','x-csrf-token':session.csrf_token,...extra},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal});
  const value=await readApiBody(response);
  if(!response.ok){if(response.status===401||response.status===403){clearClientSession();setRevoked(true);setRecords([]);}throw new ApiError(value?.error?.code||'UPSTREAM_UNAVAILABLE',value?.error?.message||(value?'操作未确认':BUSY_MESSAGE));}
  if(!value)throw new ApiError('UPSTREAM_UNAVAILABLE',BUSY_MESSAGE);
  if(method!=='GET')invalidateClientData(scope);
  return value.data as any;
 }
 async function load(target=cursor,initial=false){
  const version=++generation.current;active.current?.abort();const controller=new AbortController();active.current=controller;
  if(initial)setLoading(true);else setRefreshing(true);setError(null);
  const started=Date.now(),path='/api/v1/hunter/signals?'+new URLSearchParams({...query,limit:'100',...(target?{cursor:target}:{})});
  try{const [original,subscriptions]=await Promise.all([readClientData(scope,path,()=>api(path,'GET',undefined,{},AbortSignal.timeout(12000)),750),loadTrackingSubscriptions(scope,true).catch(()=>[])]);
   const page={...original,items:original.items.map((item:DiscoveryDTO)=>({...item}))};
   for (const item of page.items) if(item.review_state==='tracking') {
    const sub=subscriptions.find(s=>s.project_id===item.project_id);
    item.monitoring_state=sub?.error_code?'failed':sub?.desired_state==='running'&&sub.observed_state==='running'&&sub.connection==='connected'?'succeeded':'pending';
    item.monitoring_message=sub?.error_code?'失败：'+sub.error_code:item.monitoring_state==='succeeded'?'追踪中':sub?.desired_state==='removed'?'追踪已移除':sub?.desired_state==='stopped'?'追踪已停止':sub?'监听连接中':'订阅投递中或追踪服务暂不可用';
   }
   if(version!==generation.current||controller.signal.aborted)return;readAt.current=started;setRecords(page.items);setNextCursor(page.next_cursor);
   saveClientData(scope,'hunter:view',{records:page.items,nextCursor:page.next_cursor,cursor:target,history,query,counts,filterValues});
   for(const item of page.items)if(item.project_id&&homeWanted.current.has(item.discovery_id))void homeAdd(item.project_id).then(()=>forgetHome(item.discovery_id)).catch(()=>{});
  }catch(e){if(controller.signal.aborted)return;setError(e instanceof Error?e.message:'列表不可用');}
  finally{if(version===generation.current){setLoading(false);setRefreshing(false);}}
 }
 const loadRef=useRef(load);loadRef.current=load;
 useEffect(()=>{void loadRef.current(cursor,!snapshot);const poll=setInterval(()=>void loadRef.current(),10000);return()=>{clearInterval(poll);active.current?.abort();generation.current++;};},[cursor,query]);
 useEffect(()=>{
  if(revoked)return;
  const source=new EventSource('/api/v1/hunter/events'),abort=new AbortController();
  let closed=false,busy=false,again=false,checking=false,timer:ReturnType<typeof setTimeout>|undefined;
  const refresh=(event?:Event)=>{
   if(closed)return;
   if(event){try{const data=JSON.parse((event as MessageEvent).data).data;const known=currentRecords.current.find(row=>row.discovery_id===data.discovery_id);if(known&&data.revision<=known.revision)return;const at=Date.parse(data.updated_at||data.last_seen_at||data.discovered_at||'');if(Number.isFinite(at)&&at<=readAt.current)return;}catch{return;}}
   if(busy){again=true;return;}
   if(timer)return;
   timer=setTimeout(()=>{timer=undefined;if(closed)return;busy=true;void loadRef.current().finally(()=>{busy=false;if(again){again=false;refresh();}});},250);
  };
  source.addEventListener('hunter.discovery.updated',refresh);source.addEventListener('command.updated',refresh);
  source.onerror=()=>{
   if(closed||checking)return;checking=true;
   void fetch('/api/v1/auth/me',{cache:'no-store',signal:AbortSignal.any([abort.signal,AbortSignal.timeout(5000)])}).then(async response=>{
    const sessionNow=response.ok?(await response.json()).data:null;
    if(response.status===401||response.status===403||sessionNow&&(sessionNow.role!==session.role||sessionNow.must_change_password)){
     source.close();setRevoked(true);setRecords([]);
    }else if(!closed)setError('事件流暂不可用，当前保留上次结果；来源仍未连接。');
   }).catch(()=>{if(!closed)setError('事件流暂不可用，当前保留上次结果。');}).finally(()=>{checking=false;});
  };
  return()=>{closed=true;source.close();abort.abort();clearTimeout(timer);};
 },[revoked,session.role,scope]);
 const homeWanted=useRef<Set<string>>((()=>{try{return new Set<string>(JSON.parse(localStorage.getItem('ikun-hunter-home-wanted')||'[]'));}catch{return new Set<string>();}})());
 const keepHome=()=>{try{localStorage.setItem('ikun-hunter-home-wanted',JSON.stringify([...homeWanted.current]));}catch{/* per-browser convenience only */}};
 const forgetHome=(id:string)=>{homeWanted.current.delete(id);keepHome();};
 async function homeAdd(projectId:string){
  const project=await api('/api/v1/projects/'+encodeURIComponent(projectId));
  if(project.home_membership==='active')return 'already';
  await api('/api/v1/projects/'+encodeURIComponent(projectId)+'/home-membership','POST',{action:'add'},{'if-match':'"rev-'+project.revision+'"','idempotency-key':crypto.randomUUID()});
  return 'added';
 }
 const manageable=!revoked&&session.role==='superadmin'&&!session.must_change_password&&session.capabilities.can_manage_hunter;
 async function save(project:Project):Promise<Outcome>{
  if(!manageable)return {ok:false,error:{code:'FORBIDDEN',message:'当前账号只读'}};
  const row=records.find(item=>item.discovery_id===project.id);if(!row)return {ok:false,error:{code:'NOT_FOUND',message:'发现记录已不可用，请刷新核对'}};
  if(pending.current.has(project.id))return {ok:false,error:{code:'CONFLICT',message:'操作正在核对'}};
  const body={name:project.name,description:project.description,website_url:project.website||null,notes:project.notes,rating:project.grade,category:project.category||null},serialized=JSON.stringify(body);
  let operation=researchOps.current.get(project.id);
  if(operation&&operation.body!==serialized)return {ok:false,error:{code:'CONFLICT',message:'原保存结果待核实，请保持原草稿重试核对'}};
  if(!operation){try{const fresh:DiscoveryDTO=await api('/api/v1/hunter/discoveries/'+encodeURIComponent(project.id));operation={key:crypto.randomUUID(),body:serialized,revision:fresh.revision};researchOps.current.set(project.id,operation);}catch(e){return {ok:false,error:{code:'UPSTREAM_UNAVAILABLE',message:e instanceof Error?e.message:'最新版本读取失败'}};}}
  pending.current.add(project.id);
  try{
   const path='/api/v1/hunter/discoveries/'+encodeURIComponent(project.id);
   await api(path,'PATCH',body,{'if-match':'"rev-'+operation.revision+'"','idempotency-key':operation.key});
   const current:DiscoveryDTO=await api(path);setRecords(old=>old.map(item=>item.discovery_id===current.discovery_id?current:item));invalidateTrackingSubscriptions(scope);void loadRef.current();
   researchOps.current.delete(project.id);setResearchUnknown(old=>{const next=new Set(old);next.delete(project.id);return next;});
   return {ok:true,message:'研究资料已保存。',project:toProject(current)};
  }catch(e){
   const code=e instanceof ApiError?e.code:'UPSTREAM_TIMEOUT';
   if(['FORBIDDEN','VALIDATION_ERROR','VERSION_CONFLICT','CONFLICT','NOT_FOUND'].includes(code)){researchOps.current.delete(project.id);setResearchUnknown(old=>{const next=new Set(old);next.delete(project.id);return next;});}
   else setResearchUnknown(old=>new Set([...old,project.id]));
   return {ok:false,error:{code,message:e instanceof Error?e.message:'保存结果待核实，请保持原草稿重试核对'}};
  }finally{pending.current.delete(project.id);}
 }
 async function confirm(project:Project):Promise<Outcome>{
  if(!manageable)return {ok:false,error:{code:'FORBIDDEN',message:'当前账号只读'}};
  const initialRow=records.find(item=>item.discovery_id===project.id);if(!initialRow)return {ok:false,error:{code:'NOT_FOUND',message:'发现记录不在当前页'}};let row:DiscoveryDTO=initialRow;
  if(pending.current.has(project.id)||blockedIds.has(project.id)||researchOps.current.has(project.id))return {ok:false,error:{code:'CONFLICT',message:'该操作已提交或待核实，请核对原结果'}};
  if(!operations.current.has(project.id)){try{row=await api('/api/v1/hunter/discoveries/'+encodeURIComponent(project.id));}catch(e){return {ok:false,error:{code:'UPSTREAM_UNAVAILABLE',message:e instanceof Error?e.message:'最新版本读取失败'}};}}
  if(row!.review_state==='tracking')return {ok:false,error:{code:'CONFLICT',message:'已加入追踪，请刷新核对'}};
  const fields:ProjectFields={...row.project,name:project.name,description:project.description,website_url:project.website||null,notes:project.notes,rating:project.grade,category:project.category||null};
  const body={confirmed:true,project:fields};const serialized=JSON.stringify(body);let operation=operations.current.get(project.id);
  if(operation&&operation.body!==serialized)return {ok:false,error:{code:'CONFLICT',message:'原确认结果尚未核实，不能替换资料重试'}};
  if(!operation){operation={key:crypto.randomUUID(),body:serialized};operations.current.set(project.id,operation);}
  pending.current.add(project.id);setBlockedIds(old=>new Set([...old,project.id]));
  try{
   const result:CommandResult=await api('/api/v1/hunter/discoveries/'+encodeURIComponent(row.discovery_id)+'/monitoring-requests','POST',body,{'if-match':'"rev-'+row.revision+'"','idempotency-key':operation.key});
   // 202 only acknowledges durable receipt; it never becomes "joined/running" here.
   setRecords(old=>old.map(item=>item.discovery_id===row.discovery_id?{...item,monitoring_state:result.state,review_state:'tracking'}:item));
   invalidateTrackingSubscriptions(scope);void load();return {ok:true,message:'已提交加入追踪，页面将自动显示追踪状态或失败原因。'};
  }catch(e){
   const code=e instanceof ApiError?e.code:'UPSTREAM_TIMEOUT';
   if(['FORBIDDEN','VALIDATION_ERROR','VERSION_CONFLICT','CONFLICT','NOT_FOUND'].includes(code)){operations.current.delete(project.id);setBlockedIds(old=>{const next=new Set(old);next.delete(project.id);return next;});}
   return {ok:false,error:{code,message:e instanceof Error?e.message:'确认结果待核实；禁止重复提交'}};
  }finally{pending.current.delete(project.id);}
 }
 async function ignore(project:Project):Promise<Outcome>{
  if(!manageable)return {ok:false,error:{code:'FORBIDDEN',message:'当前账号只读'}};
  const row=records.find(item=>item.discovery_id===project.id);if(!row)return {ok:false,error:{code:'NOT_FOUND',message:'发现记录已不可用，请刷新核对'}};
  if(pending.current.has(project.id))return {ok:false,error:{code:'CONFLICT',message:'操作正在核对'}};
  pending.current.add(project.id);
  try{
   const fresh:DiscoveryDTO=await api('/api/v1/hunter/discoveries/'+encodeURIComponent(project.id));await api('/api/v1/hunter/discoveries/'+encodeURIComponent(project.id),'PATCH',{ignored:true},{'if-match':'"rev-'+fresh.revision+'"','idempotency-key':crypto.randomUUID()});
   setRecords(old=>old.filter(item=>item.discovery_id!==project.id));void load();
   return {ok:true,message:'已忽略「'+project.name+'」，不再显示。'};
  }catch(e){return {ok:false,error:{code:e instanceof ApiError?e.code:'UPSTREAM_TIMEOUT',message:e instanceof Error?e.message:'忽略未确认，请刷新核对'}};}
  finally{pending.current.delete(project.id);}
 }
 async function addHome(project:Project):Promise<Outcome>{
  if(!manageable)return {ok:false,error:{code:'FORBIDDEN',message:'当前账号只读'}};
  const row=records.find(item=>item.discovery_id===project.id);if(!row)return {ok:false,error:{code:'NOT_FOUND',message:'发现记录已不可用，请刷新核对'}};
  if(row.project_id){
   try{const result=await homeAdd(row.project_id);return {ok:true,message:result==='already'?'「'+project.name+'」已在主页':'「'+project.name+'」已加入主页'};}
   catch(e){return {ok:false,error:{code:e instanceof ApiError?e.code:'UPSTREAM_TIMEOUT',message:e instanceof Error?e.message:'加入主页未确认'}};}
  }
  // Not tracked yet: owner decision — join tracking, then add to home once the project exists.
  homeWanted.current.add(project.id);keepHome();
  if(row.review_state==='tracking'||pending.current.has(project.id))return {ok:true,message:'已在加入追踪中；项目建好后会自动放到主页。'};
  const joined=await confirm(project);
  if(!joined.ok){if(!['UPSTREAM_TIMEOUT'].includes(joined.error.code))forgetHome(project.id);return joined;}
  return {ok:true,message:'已提交加入追踪；项目建好后会自动放到主页。'};
 }
 async function accountPages(){
  let cursor:string|null=null;const accounts:HunterAccountDTO[]=[];
  do{const page=await api('/api/v1/hunter/accounts?limit=100'+(cursor?'&cursor='+encodeURIComponent(cursor):''));accounts.push(...page.items);cursor=page.next_cursor;}while(cursor);
  setCounts({total:accounts.length,enabled:accounts.filter(item=>item.enabled).length});return accounts;
 }
 async function manage(action:'add'|'enable'|'disable'|'remove',handle:string):Promise<Outcome>{
  if(!manageable)return {ok:false,error:{code:'FORBIDDEN',message:'当前账号只读'}};
  if(pending.current.has('accounts')||pending.current.has('accounts-unknown'))return {ok:false,error:{code:'CONFLICT',message:'管理操作处理中或结果待核实；禁止重复提交'}};
  pending.current.add('accounts');
  try{
   if(action==='add')await api('/api/v1/hunter/accounts','POST',{x_handle:handle,label:'',notes:'',enabled:true},{'idempotency-key':crypto.randomUUID()});
   else{const item=(await accountPages()).find(account=>account.x_handle.toLowerCase()===handle.toLowerCase());if(!item)throw new ApiError('NOT_FOUND','未找到指定猎手');
    await api('/api/v1/hunter/accounts/'+item.account_id,action==='remove'?'DELETE':'PATCH',action==='remove'?{}:{enabled:action==='enable'},{'idempotency-key':crypto.randomUUID(),'if-match':'"rev-'+item.revision+'"'});}
   await accountPages();return {ok:true,message:'猎手本地配置已保存；不代表来源覆盖或远端监控已生效。'};
  }catch(e){const code=e instanceof ApiError?e.code:'UPSTREAM_TIMEOUT';if(!['FORBIDDEN','VALIDATION_ERROR','VERSION_CONFLICT','CONFLICT','NOT_FOUND'].includes(code))pending.current.add('accounts-unknown');return {ok:false,error:{code,message:e instanceof Error?e.message:'操作结果待核实，请先核对配置'}};}
  finally{pending.current.delete('accounts');}
 }
 const projects:Project[]=records.map(toProject);
 const updateFilter=(key:string,value:string)=>{setCursor(null);setHistory([]);setQuery(old=>{const next={...old};if(key==='query'){if(value)next.q=value;else delete next.q;}if(key==='grade'){if(value!=='all')next.rating=value==='none'?'unrated':value;else delete next.rating;}if(key==='status'){if(value!=='all')next.review_state=value==='joined'?'tracking':value;else delete next.review_state;}if(key==='time'){delete next.since;delete next.until;if(value!=='all'){next.since=new Date(Date.now()-Number(value)*3600000).toISOString();next.until=new Date().toISOString();}}return JSON.stringify(old)===JSON.stringify(next)?old:next;});};
 const binding:LiveBinding={initialFilters:filterValues,projects,role:revoked?'user':session.role,loading,refreshing,error,fixture,nextCursor,previous:history.length>0,counts,filter:(key,value)=>{setFilterValues(old=>({...old,[key]:value}));updateFilter(key,value);},
  blockedIds:new Set([...blockedIds,...researchUnknown,...records.filter(item=>!!item.monitoring_state&&item.monitoring_state!=='failed').map(item=>item.discovery_id)]),confirm,ignore,addHome,save,manage,refresh:()=>{void load();},
  next:()=>{if(nextCursor&&!refreshing&&!loading){setHistory(old=>[...old,cursor]);setCursor(nextCursor);}},back:()=>{if(history.length&&!refreshing&&!loading){setCursor(history.at(-1)!);setHistory(old=>old.slice(0,-1));}}};
 return <App live={binding}/>;
}
