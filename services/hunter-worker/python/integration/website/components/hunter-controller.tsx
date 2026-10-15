'use client';
import {useEffect,useRef,useState} from 'react';
import App from '../features/hunter-discovery/v3/App';
import type {Project,Grade} from '../features/hunter-discovery/v3/model';
import type {DiscoveryDTO,CommandResult,HunterAccountDTO,ProjectFields} from '../features/hunter-discovery/model';
import './hunter-host.css';

type Session={role:'superadmin'|'user';csrf_token:string;must_change_password:boolean;capabilities:{can_manage_hunter:boolean}};
type PublicError={code:string;message:string};
type Outcome={ok:true;message:string;project?:Project}|{ok:false;error:PublicError};
const toProject=(row:DiscoveryDTO):Project=>({id:row.discovery_id,name:row.project.name,handle:row.x_handle,bio:row.profile_bio,hunters:row.signal_count,grade:row.project.rating as Grade,
 status:row.review_state==='reviewed'?'reviewed':'pending',foundAt:row.discovered_at?Date.parse(row.discovered_at):NaN,website:row.project.website_url||'',description:row.project.description,token:'unknown',notes:row.project.notes,watch:false});
export interface LiveBinding{
 projects:Project[];role:'superadmin'|'user';loading:boolean;refreshing:boolean;error:string|null;
 fixture:boolean;nextCursor:string|null;previous:boolean;blockedIds:ReadonlySet<string>;
 counts:{total:number;enabled:number}|null;
 confirm:(project:Project)=>Promise<Outcome>;save:(project:Project)=>Promise<Outcome>;manage:(action:'add'|'enable'|'disable'|'remove',handle:string)=>Promise<Outcome>;
 refresh:()=>void;next:()=>void;back:()=>void;
 filter:(key:string,value:string)=>void;
}
class ApiError extends Error{constructor(readonly code:string,message:string){super(message)}}
export default function HunterController({session,fixture=false}:{session:Session;fixture?:boolean}){
 const [records,setRecords]=useState<DiscoveryDTO[]>([]),[loading,setLoading]=useState(true),[refreshing,setRefreshing]=useState(false),[error,setError]=useState<string|null>(null);
 const [nextCursor,setNextCursor]=useState<string|null>(null),[cursor,setCursor]=useState<string|null>(null),[history,setHistory]=useState<(string|null)[]>([]),[counts,setCounts]=useState<{total:number;enabled:number}|null>(null);
 const [blockedIds,setBlockedIds]=useState<ReadonlySet<string>>(new Set()),pending=useRef(new Set<string>()),operations=useRef(new Map<string,{key:string;body:string}>());
 const [query,setQuery]=useState<Record<string,string>>({}),[revoked,setRevoked]=useState(false);
 const researchOps=useRef(new Map<string,{key:string;body:string;revision:number}>());
 const [researchUnknown,setResearchUnknown]=useState<ReadonlySet<string>>(new Set());
 const generation=useRef(0),active=useRef<AbortController|null>(null);
 async function api(path:string,method='GET',body?:unknown,extra:Record<string,string>={},signal?:AbortSignal){
  const response=await fetch(path,{method,headers:{'content-type':'application/json','x-csrf-token':session.csrf_token,...extra},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal});
  const value=await response.json();if(!response.ok){if(response.status===401||response.status===403){setRevoked(true);setRecords([]);}throw new ApiError(value.error?.code||'UPSTREAM_UNAVAILABLE',value.error?.message||'操作未确认');}return value.data;
 }
 async function load(target=cursor,initial=false){
  const version=++generation.current;active.current?.abort();const controller=new AbortController();active.current=controller;
  if(initial)setLoading(true);else setRefreshing(true);setError(null);
  try{const page=await api('/api/v1/hunter/signals?'+new URLSearchParams({...query,limit:'100',...(target?{cursor:target}:{})}),'GET',undefined,{},controller.signal);
   if(version!==generation.current)return;setRecords(page.items);setNextCursor(page.next_cursor);
  }catch(e){if(controller.signal.aborted)return;setError(e instanceof Error?e.message:'列表不可用');}
  finally{if(version===generation.current){setLoading(false);setRefreshing(false);}}
 }
 useEffect(()=>{void load(cursor,records.length===0);return()=>active.current?.abort();},[cursor,query]);
 const manageable=!revoked&&session.role==='superadmin'&&!session.must_change_password&&session.capabilities.can_manage_hunter;
 async function save(project:Project):Promise<Outcome>{
  if(!manageable)return {ok:false,error:{code:'FORBIDDEN',message:'当前账号只读'}};
  const row=records.find(item=>item.discovery_id===project.id);if(!row)return {ok:false,error:{code:'NOT_FOUND',message:'发现记录已不可用，请刷新核对'}};
  if(pending.current.has(project.id))return {ok:false,error:{code:'CONFLICT',message:'操作正在核对'}};
  const body={name:project.name,description:project.description,website_url:project.website||null,notes:project.notes,rating:project.grade},serialized=JSON.stringify(body);
  let operation=researchOps.current.get(project.id);
  if(operation&&operation.body!==serialized)return {ok:false,error:{code:'CONFLICT',message:'原保存结果待核实，请保持原草稿重试核对'}};
  if(!operation){operation={key:crypto.randomUUID(),body:serialized,revision:row.revision};researchOps.current.set(project.id,operation);}
  pending.current.add(project.id);
  try{
   const path='/api/v1/hunter/discoveries/'+encodeURIComponent(project.id);
   await api(path,'PATCH',body,{'if-match':'"rev-'+operation.revision+'"','idempotency-key':operation.key});
   const current:DiscoveryDTO=await api(path);setRecords(old=>old.map(item=>item.discovery_id===current.discovery_id?current:item));
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
  const row=records.find(item=>item.discovery_id===project.id);if(!row)return {ok:false,error:{code:'NOT_FOUND',message:'发现记录不在当前页'}};
  if(pending.current.has(project.id)||blockedIds.has(project.id)||researchOps.current.has(project.id))return {ok:false,error:{code:'CONFLICT',message:'该操作已提交或待核实，请核对原结果'}};
  const fields:ProjectFields={...row.project,name:project.name,description:project.description,website_url:project.website||null,notes:project.notes,rating:project.grade};
  const body={confirmed:true,project:fields};const serialized=JSON.stringify(body);let operation=operations.current.get(project.id);
  if(operation&&operation.body!==serialized)return {ok:false,error:{code:'CONFLICT',message:'原确认结果尚未核实，不能替换资料重试'}};
  if(!operation){operation={key:crypto.randomUUID(),body:serialized};operations.current.set(project.id,operation);}
  pending.current.add(project.id);setBlockedIds(old=>new Set([...old,project.id]));
  try{
   const result:CommandResult=await api('/api/v1/hunter/discoveries/'+encodeURIComponent(row.discovery_id)+'/monitoring-requests','POST',body,{'if-match':'"rev-'+row.revision+'"','idempotency-key':operation.key});
   // 202 only acknowledges durable receipt; it never becomes "joined/running" here.
   setRecords(old=>old.map(item=>item.discovery_id===row.discovery_id?{...item,monitoring_state:result.state,review_state:'tracking'}:item));
   void load();return {ok:true,message:'人工确认已持久受理；远端监控状态仍待核实。'};
  }catch(e){
   const code=e instanceof ApiError?e.code:'UPSTREAM_TIMEOUT';
   if(['FORBIDDEN','VALIDATION_ERROR','VERSION_CONFLICT','CONFLICT','NOT_FOUND'].includes(code)){operations.current.delete(project.id);setBlockedIds(old=>{const next=new Set(old);next.delete(project.id);return next;});}
   return {ok:false,error:{code,message:e instanceof Error?e.message:'确认结果待核实；禁止重复提交'}};
  }finally{pending.current.delete(project.id);}
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
   if(action==='add')await api('/api/v1/hunter/accounts','POST',{x_handle:handle,label:'',notes:'',enabled:false},{'idempotency-key':crypto.randomUUID()});
   else{const item=(await accountPages()).find(account=>account.x_handle.toLowerCase()===handle.toLowerCase());if(!item)throw new ApiError('NOT_FOUND','未找到指定猎手');
    await api('/api/v1/hunter/accounts/'+item.account_id,action==='remove'?'DELETE':'PATCH',action==='remove'?{}:{enabled:action==='enable'},{'idempotency-key':crypto.randomUUID(),'if-match':'"rev-'+item.revision+'"'});}
   await accountPages();return {ok:true,message:'猎手本地配置已保存；不代表来源覆盖或远端监控已生效。'};
  }catch(e){const code=e instanceof ApiError?e.code:'UPSTREAM_TIMEOUT';if(!['FORBIDDEN','VALIDATION_ERROR','VERSION_CONFLICT','CONFLICT','NOT_FOUND'].includes(code))pending.current.add('accounts-unknown');return {ok:false,error:{code,message:e instanceof Error?e.message:'操作结果待核实，请先核对配置'}};}
  finally{pending.current.delete('accounts');}
 }
 const projects:Project[]=records.map(toProject);
 const updateFilter=(key:string,value:string)=>{setCursor(null);setHistory([]);setQuery(old=>{const next={...old};if(key==='query'){if(value)next.q=value;else delete next.q;}if(key==='grade'){if(value!=='all')next.rating=value==='none'?'unrated':value;else delete next.rating;}if(key==='status'){if(value!=='all')next.review_state=value==='joined'?'tracking':value;else delete next.review_state;}if(key==='time'){delete next.since;delete next.until;if(value!=='all'){next.since=new Date(Date.now()-Number(value)*3600000).toISOString();next.until=new Date().toISOString();}}return next;});};
 const binding:LiveBinding={projects,role:revoked?'user':session.role,loading,refreshing,error,fixture,nextCursor,previous:history.length>0,counts,filter:updateFilter,
  blockedIds:new Set([...blockedIds,...researchUnknown,...records.filter(item=>!!item.monitoring_state&&item.monitoring_state!=='failed').map(item=>item.discovery_id)]),confirm,save,manage,refresh:()=>{void load();},
  next:()=>{if(nextCursor&&!refreshing&&!loading){setHistory(old=>[...old,cursor]);setCursor(nextCursor);}},back:()=>{if(history.length&&!refreshing&&!loading){setCursor(history.at(-1)!);setHistory(old=>old.slice(0,-1));}}};
 return <App live={binding}/>;
}
