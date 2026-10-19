'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {Button} from '@ikun/ui';
import ReferenceHomepage from './homepage-ui/reference-homepage';
import type {ArchiveNote,EditorDraft,ProjectMilestone,ReferenceCallbacks} from '../features/homepage/reference-types';
import type {HomepageContext,HomepageData,HomepageQuery,OperationResult,ProjectRecordProjection,ProjectRef,PublicError} from '../features/homepage/types';
import {canEdit} from '../features/homepage/view-model';
import './projects-home-access.css';
type Home={project:ProjectRecordProjection;milestone:Omit<ProjectMilestone,'project_id'>;completion:null|{previous_stage:ArchiveNote['previous_stage'];completed_at:string}};
type Page={items:Home[];total:number;next_cursor:string|null};
type MainQuery={q:string;rating:string;progress_stage:string;discovered_on:string;category:string;sort:string;direction:'asc'|'desc'};
const emptyPage:Page={items:[],total:0,next_cursor:null};
const initial:MainQuery={q:'',rating:'all',progress_stage:'all',discovered_on:'',category:'all',sort:'discovered',direction:'desc'};
const emptySummary={tracked_total:0,by_rating:{S:0,A:0,B:0},completed_total:0,other_total:0};
type Pending={key:string;path:string;method:string;contract:string};
function publicError(value:unknown):PublicError{const data=value as {error?:{code?:string;message?:string;retryable?:boolean};request_id?:string};return {code:data?.error?.code??'UPSTREAM_UNAVAILABLE',message:data?.error?.message??'项目数据暂不可用',retryable:data?.error?.retryable===true,request_id:data?.request_id??null};}
async function read(path:string,signal?:AbortSignal){const response=await fetch(path,{signal,cache:'no-store'});const value=await response.json();if(!response.ok)throw publicError(value);return value.data;}
function params(query:MainQuery,limit=9){const out=new URLSearchParams({view:'home-v1',collection:'tracked',limit:String(limit),sort:query.sort,direction:query.direction});for(const key of ['q','rating','progress_stage','discovered_on','category'] as const)if(query[key]&&query[key]!=='all')out.set(key,query[key]);return out;}

export default function ProjectsHome({context,csrf,userId}:{context:HomepageContext;csrf:string;userId:string}){
  const canWrite=canEdit(context);
  const [query,setQuery]=useState(initial),[main,setMain]=useState<Page>(emptyPage),[completed,setCompleted]=useState<Page>(emptyPage),[other,setOther]=useState<Page>(emptyPage);
  const [summary,setSummary]=useState(emptySummary),[events,setEvents]=useState<Home[]>([]),[asOf,setAsOf]=useState<string>(),[windowDays,setWindow]=useState('7'),[xHandles,setXHandles]=useState<Record<string,string>>({});
  const [detail,setDetail]=useState<Home|null>(null),[error,setError]=useState<PublicError|null>(null),[loading,setLoading]=useState(true),[version,setVersion]=useState(0),[page,setPage]=useState(1);
  const [completedIndex,setCompletedIndex]=useState(1),[otherIndex,setOtherIndex]=useState(1);
  const [completedLoaded,setCompletedLoaded]=useState(0),[otherLoaded,setOtherLoaded]=useState(0);
  // X account per project comes from the tracking subscriptions (owner: link each project to its X profile).
  useEffect(()=>{const abort=new AbortController();(async()=>{const map:Record<string,string>={};let cursor:string|null=null;
    do{const data:any=await read('/api/v1/tracking/subscriptions?limit=100'+(cursor?'&cursor='+encodeURIComponent(cursor):''),abort.signal);
      for(const row of data.items??[])if(row.project_id&&row.x_handle&&row.desired_state!=='removed')map[row.project_id]=row.x_handle;cursor=data.next_cursor??null;}while(cursor);
    if(!abort.signal.aborted)setXHandles(map);})().catch(()=>{});return()=>abort.abort();},[version]);
  const [limit,setLimit]=useState(9);const fitRef=useRef<()=>void>(()=>{});
  const pageRef=useRef(1);pageRef.current=page;
  const mainCursors=useRef<(string|null)[]>([null]),completedCursors=useRef<(string|null)[]>([null]),otherCursors=useRef<(string|null)[]>([null]);
  const epoch=useRef(0),pending=useRef<Pending|null>(null);const storageKey='ikun-project-operation:'+userId;
  useEffect(()=>{try{const raw=sessionStorage.getItem(storageKey);if(raw)pending.current=JSON.parse(raw);}catch{}},[storageKey]);
  const persist=(value:Pending|null)=>{pending.current=value;try{if(value)sessionStorage.setItem(storageKey,JSON.stringify(value));else sessionStorage.removeItem(storageKey);}catch{}};
  const reload=()=>setVersion(v=>v+1);
  useEffect(()=>{const generation=++epoch.current;const abort=new AbortController();setLoading(true);setError(null);
    const search=params(query,limit);const cursor=mainCursors.current[page-1];if(cursor)search.set('cursor',cursor);
    read('/api/v1/projects?'+search,abort.signal).then(data=>{if(generation===epoch.current){setMain(data);mainCursors.current[page]=data.next_cursor;}}).catch(e=>{if(!abort.signal.aborted&&generation===epoch.current)setError(e);}).finally(()=>{if(generation===epoch.current)setLoading(false);});
    return()=>abort.abort();
  },[query,page,version,limit]);
  // Fill the table: rows per page follow the available height (owner request).
  useEffect(()=>{if(typeof ResizeObserver==='undefined')return;let ro:ResizeObserver|null=null,timer:ReturnType<typeof setTimeout>|undefined,onResize:(()=>void)|null=null;
    // Bug fix 2026-10-19: rows have different heights per page, so re-fitting on page 2+ changed the limit and
    // bounced the user back to page 1. Only size the page while on page 1; later pages keep that size.
    const fit=fitRef.current=()=>{if(pageRef.current!==1)return;const box=document.querySelector('.hpv2-project-grid .ik-table-scroll');const rows=box?.querySelectorAll('tbody tr');if(!box||!rows||rows.length<2)return;const last=rows[rows.length-1].getBoundingClientRect(),first=rows[0].getBoundingClientRect();const rowH=(last.bottom-first.top)/rows.length;if(!(rowH>10))return;const grid=box.closest('.hpv2-project-grid');const footer=grid?.parentElement?.querySelector('.hpv2-table-footer');const bottom=Math.max(box.getBoundingClientRect().bottom,grid?grid.getBoundingClientRect().bottom:0,footer?footer.getBoundingClientRect().top:0);const free=bottom-last.bottom;const n=Math.max(5,Math.min(100,rows.length+Math.floor((free+2)/rowH)));setLimit(old=>{if(old===n)return old;mainCursors.current=[null];setPage(1);return n;});};
    const attach=()=>{const box=document.querySelector('.hpv2-project-grid .ik-table-scroll');if(!box){timer=setTimeout(attach,300);return;}const kick=()=>{clearTimeout(timer);timer=setTimeout(fit,150);};ro=new ResizeObserver(kick);ro.observe(box);const grid=box.closest('.hpv2-project-grid');if(grid){ro.observe(grid);if(grid.parentElement)ro.observe(grid.parentElement);}window.addEventListener('resize',kick);onResize=kick;};attach();
    return()=>{ro?.disconnect();clearTimeout(timer);if(onResize)window.removeEventListener('resize',onResize);};},[]);
  useEffect(()=>{if(!loading){const t=setTimeout(()=>fitRef.current(),50);return()=>clearTimeout(t);}},[loading]);
  useEffect(()=>{const abort=new AbortController();const suffix=query.discovered_on?'?discovered_on='+query.discovered_on:'';read('/api/v1/projects/home-summary'+suffix,abort.signal).then(setSummary).catch(e=>{if(!abort.signal.aborted)setError(e);});return()=>abort.abort();},[query.discovered_on,version]);
  useEffect(()=>{const abort=new AbortController();const search=new URLSearchParams({window_days:windowDays,limit:'100'});if(query.rating!=='all')search.set('rating',query.rating);read('/api/v1/projects/milestones?'+search,abort.signal).then(data=>{if(!abort.signal.aborted){setEvents(data.items.map((p:Home)=>({...p,completion:null})));setAsOf(data.as_of_date);}}).catch(e=>{if(!abort.signal.aborted)setError(e);});return()=>abort.abort();},[query.rating,windowDays,version]);
  useEffect(()=>{const abort=new AbortController();const search=new URLSearchParams({view:'home-v1',collection:'completed',limit:'9'});const cursor=completedCursors.current[completedIndex-1];if(cursor)search.set('cursor',cursor);read('/api/v1/projects?'+search,abort.signal).then(data=>{if(!abort.signal.aborted){setCompleted(data);setCompletedLoaded(completedIndex);completedCursors.current[completedIndex]=data.next_cursor;}}).catch(e=>{if(!abort.signal.aborted)setError(e);});return()=>abort.abort();},[completedIndex,version]);
  useEffect(()=>{const abort=new AbortController();const search=new URLSearchParams({view:'home-v1',collection:'other',limit:'9'});const cursor=otherCursors.current[otherIndex-1];if(cursor)search.set('cursor',cursor);read('/api/v1/projects?'+search,abort.signal).then(data=>{if(!abort.signal.aborted){setOther(data);setOtherLoaded(otherIndex);otherCursors.current[otherIndex]=data.next_cursor;}}).catch(e=>{if(!abort.signal.aborted)setError(e);});return()=>abort.abort();},[otherIndex,version]);
  function change(next:Partial<MainQuery>){mainCursors.current=[null];setPage(1);setQuery(q=>({...q,...next}));}
  function canPage(next:number){return !loading&&Number.isInteger(next)&&next>=1&&(next===1||typeof mainCursors.current[next-1]==='string');}
  function operationError(value:unknown,state:OperationResult['state']='failed'):OperationResult{const error=publicError(value);return {state,request_id:error.request_id,error};}
  async function reconcile():Promise<OperationResult>{
    const saved=pending.current;if(!saved)return {state:'failed',request_id:null,error:{code:'NOT_FOUND',message:'没有待核对的原操作',retryable:false,request_id:null}};
    try{const search=new URLSearchParams({method:saved.method,path:saved.path,contract:saved.contract});await read('/api/v1/projects/operations/'+saved.key+'?'+search);persist(null);reload();return {state:'succeeded',request_id:null};}catch(e){const error=e as PublicError;return {state:'unknown',request_id:error.request_id,error:{...error,message:error.code==='NOT_FOUND'?'尚未找到原操作回执；结果仍待核对，请勿重复提交':error.message}};}
  }
  async function write(path:string,method:string,body:unknown,target?:ProjectRef,home=true):Promise<OperationResult>{
    if(!canWrite)return operationError({error:{code:'FORBIDDEN',message:'当前账号只读，不能修改项目资料',retryable:false}});
    if(pending.current){const checked=await reconcile();return checked.state==='succeeded'?operationError({error:{code:'CONFLICT',message:'原操作已核对完成，请重新检查资料后提交当前操作'}}):checked;}
    const saved={key:crypto.randomUUID(),path,method,contract:home?'projects-home-v1':'phase2-v1.0.0'};persist(saved);
    try{const response=await fetch(path+(home?'?view=home-v1':''),{method,headers:{'content-type':'application/json','x-csrf-token':csrf,'idempotency-key':saved.key,...(target?{'if-match':`"rev-${target.revision}"`}:{})},...(method==='DELETE'?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(10000)});const value=await response.json();
      if(!response.ok){if(response.status<500){persist(null);if(response.status===409)reload();}return operationError(value,response.status>=500?'unknown':'failed');}
      persist(null);mainCursors.current=[null];completedCursors.current=[null];otherCursors.current=[null];setPage(1);setCompletedIndex(1);setOtherIndex(1);setDetail(null);reload();return {state:'succeeded',request_id:value.request_id};
    }catch{return operationError({error:{code:'UPSTREAM_TIMEOUT',message:'写入结果待核对，保留原幂等键'},request_id:null},'unknown');}
  }
  // 2026-10-17 product decision: removing/completing/deleting a homepage project also stops its tweet tracking
  // (the Tracking delete command also removes ikun's own 6551 NEW_TWEET Watch entry). Best-effort, after success.
  const thenStop=(_ids:readonly string[])=>(result:OperationResult)=>result;
  // Owner 2026-10-19: inline edits in the table. Last save wins: always PATCH against the freshest revision.
  async function quickEdit(id:string,body:Record<string,unknown>):Promise<string|null>{
    if(!canWrite)return '当前账号只读';
    for(let attempt=0;attempt<2;attempt++){
      let fresh:Home;try{fresh=await read('/api/v1/projects/'+encodeURIComponent(id)+'?view=home-v1');}catch(e){return (e as PublicError).message;}
      try{const response=await fetch('/api/v1/projects/'+encodeURIComponent(id)+'?view=home-v1',{method:'PATCH',headers:{'content-type':'application/json','x-csrf-token':csrf,'idempotency-key':crypto.randomUUID(),'if-match':`"rev-${fresh.project.revision}"`},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
        const value=await response.json();
        if(response.ok){reload();return null;}
        if(response.status===409&&attempt===0)continue;
        return publicError(value).message;
      }catch{reload();return '保存结果未确认，已刷新，请核对';}
    }
    return '项目刚被修改，请重试';
  }
  async function openDetail(id:string){try{setDetail(await read('/api/v1/projects/'+id+'?view=home-v1'));}catch(e){setError(e as PublicError);}}
  const latest=new Map<string,Home>();
  for(const home of [...main.items,...completed.items,...other.items,...events,...(detail?[detail]:[])]){const previous=latest.get(home.project.project_id);if(!previous||home.project.revision>=previous.project.revision)latest.set(home.project.project_id,home);}
  const homes=[...latest.values()];
  const data:HomepageData={status:error?'error':loading&&!homes.length?'loading':homes.length?'ready':'empty',items:homes.map(p=>p.project),next_cursor:null,refreshing:loading,error};
  const pagination=(index:number,loaded:number,total:number,next:string|null,cursors:(string|null)[],move:(index:number)=>void)=><div className="hpv2-pagination"><Button size="sm" aria-label="上一页记录" disabled={index<=1||index!==loaded} onClick={()=>move(index-1)}>‹</Button><span>{index} / {Math.max(1,Math.ceil(total/9))} · {total}</span><Button size="sm" aria-label="下一页记录" disabled={!next||index!==loaded} onClick={()=>{if(index<cursors.length)move(index+1);}}>›</Button></div>;
  const draftBody=(draft:EditorDraft)=>({fields:draft.fields,milestone:draft.milestone,complete:draft.archive_after_save});
  const mutations:Pick<ReferenceCallbacks,'onCreateDraft'|'onUpdateDraft'|'onDelete'|'onMembership'|'onArchive'|'onRestore'>=canWrite?{
      onCreateDraft:draft=>write('/api/v1/projects','POST',draftBody(draft)),onUpdateDraft:(target,draft)=>write('/api/v1/projects/'+target.project_id,'PATCH',{fields:draft.fields,milestone:draft.milestone,...(draft.archive_after_save?{complete:true}:{})},target).then(draft.archive_after_save?thenStop([target.project_id]):(r:OperationResult)=>r),
      onDelete:target=>write('/api/v1/projects/'+target.project_id,'DELETE',{},target).then(thenStop([target.project_id])),onMembership:(target,action)=>write('/api/v1/projects/'+target.project_id+'/home-membership','POST',{action},target).then(action==='remove'?thenStop([target.project_id]):(r:OperationResult)=>r),
      onArchive:targets=>write('/api/v1/projects/completions','POST',{items:targets.map(t=>({project_id:t.project_id,revision:t.revision}))}).then(thenStop(targets.map(t=>t.project_id))),onRestore:target=>write('/api/v1/projects/'+target.project_id+'/restore','POST',{},target)}:{};
  return <div className="projects-home-access" data-project-access={canWrite?'write':'readonly'}><ReferenceHomepage context={context} data={data} milestones={homes.map(p=>({...p.milestone,project_id:p.project.project_id}))} archiveNotes={homes.flatMap(p=>p.completion?[{project_id:p.project.project_id,previous_stage:p.completion.previous_stage,completed_on:p.completion.completed_at}]:[])} asOfDate={asOf}
    callbacks={{...mutations,onReconcile:reconcile,
      onQueryChange:(q:HomepageQuery)=>change({q:q.q,rating:q.rating,progress_stage:q.progress_stage,category:q.category??'all'}),onDiscoveryDateChange:day=>change({discovered_on:day??''}),onReload:reload}}
    server={{mainIds:main.items.map(p=>p.project.project_id),completedIds:completed.items.map(p=>p.project.project_id),otherIds:other.items.map(p=>p.project.project_id),eventIds:events.map(p=>p.project.project_id),total:main.total,page,pageSize:limit,xHandles,onQuickEdit:canWrite?quickEdit:undefined,hasNext:!!main.next_cursor,summary,
      onSort:value=>change({sort:value.key,direction:value.direction}),canPage,onPage:next=>{if(canPage(next))setPage(next);},onWindow:setWindow,onDetail:id=>void openDetail(id),
      completedPagination:pagination(completedIndex,completedLoaded,completed.total,completed.next_cursor,completedCursors.current,setCompletedIndex),otherPagination:pagination(otherIndex,otherLoaded,other.total,other.next_cursor,otherCursors.current,setOtherIndex)}}/></div>;
}
