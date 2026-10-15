'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {Button} from '@ikun/ui';
import ReferenceHomepage from './homepage-ui/reference-homepage';
import type {ArchiveNote,EditorDraft,ProjectMilestone} from '../features/homepage/reference-types';
import type {HomepageContext,HomepageData,HomepageQuery,OperationResult,ProjectRecordProjection,ProjectRef,PublicError} from '../features/homepage/types';
type Home={project:ProjectRecordProjection;milestone:Omit<ProjectMilestone,'project_id'>;completion:null|{previous_stage:ArchiveNote['previous_stage'];completed_at:string}};
type Page={items:Home[];total:number;next_cursor:string|null};
type MainQuery={q:string;rating:string;progress_stage:string;discovered_on:string;sort:string;direction:'asc'|'desc'};
const emptyPage:Page={items:[],total:0,next_cursor:null};
const initial:MainQuery={q:'',rating:'all',progress_stage:'all',discovered_on:'',sort:'discovered',direction:'desc'};
const emptySummary={tracked_total:0,by_rating:{S:0,A:0,B:0},completed_total:0,other_total:0};
type Pending={key:string;path:string;method:string;contract:string};
function publicError(value:unknown):PublicError{const data=value as {error?:{code?:string;message?:string;retryable?:boolean};request_id?:string};return {code:data?.error?.code??'UPSTREAM_UNAVAILABLE',message:data?.error?.message??'项目数据暂不可用',retryable:data?.error?.retryable===true,request_id:data?.request_id??null};}
async function read(path:string,signal?:AbortSignal){const response=await fetch(path,{signal,cache:'no-store'});const value=await response.json();if(!response.ok)throw publicError(value);return value.data;}
function params(query:MainQuery){const out=new URLSearchParams({view:'home-v1',collection:'tracked',limit:'9',sort:query.sort,direction:query.direction});for(const key of ['q','rating','progress_stage','discovered_on'] as const)if(query[key]&&query[key]!=='all')out.set(key,query[key]);return out;}

export default function ProjectsHome({context,csrf,userId}:{context:HomepageContext;csrf:string;userId:string}){
  const [query,setQuery]=useState(initial),[main,setMain]=useState<Page>(emptyPage),[completed,setCompleted]=useState<Page>(emptyPage),[other,setOther]=useState<Page>(emptyPage);
  const [summary,setSummary]=useState(emptySummary),[events,setEvents]=useState<Home[]>([]),[asOf,setAsOf]=useState<string>(),[windowDays,setWindow]=useState('all');
  const [detail,setDetail]=useState<Home|null>(null),[error,setError]=useState<PublicError|null>(null),[loading,setLoading]=useState(true),[version,setVersion]=useState(0),[page,setPage]=useState(1);
  const [completedIndex,setCompletedIndex]=useState(1),[otherIndex,setOtherIndex]=useState(1);
  const [completedLoaded,setCompletedLoaded]=useState(0),[otherLoaded,setOtherLoaded]=useState(0);
  const mainCursors=useRef<(string|null)[]>([null]),completedCursors=useRef<(string|null)[]>([null]),otherCursors=useRef<(string|null)[]>([null]);
  const epoch=useRef(0),pending=useRef<Pending|null>(null);const storageKey='ikun-project-operation:'+userId;
  useEffect(()=>{try{const raw=sessionStorage.getItem(storageKey);if(raw)pending.current=JSON.parse(raw);}catch{}},[storageKey]);
  const persist=(value:Pending|null)=>{pending.current=value;try{if(value)sessionStorage.setItem(storageKey,JSON.stringify(value));else sessionStorage.removeItem(storageKey);}catch{}};
  const reload=()=>setVersion(v=>v+1);
  useEffect(()=>{const generation=++epoch.current;const abort=new AbortController();setLoading(true);setError(null);
    const search=params(query);const cursor=mainCursors.current[page-1];if(cursor)search.set('cursor',cursor);
    read('/api/v1/projects?'+search,abort.signal).then(data=>{if(generation===epoch.current){setMain(data);mainCursors.current[page]=data.next_cursor;}}).catch(e=>{if(!abort.signal.aborted&&generation===epoch.current)setError(e);}).finally(()=>{if(generation===epoch.current)setLoading(false);});
    return()=>abort.abort();
  },[query,page,version]);
  useEffect(()=>{const abort=new AbortController();const suffix=query.discovered_on?'?discovered_on='+query.discovered_on:'';read('/api/v1/projects/home-summary'+suffix,abort.signal).then(setSummary).catch(e=>{if(!abort.signal.aborted)setError(e);});return()=>abort.abort();},[query.discovered_on,version]);
  useEffect(()=>{const abort=new AbortController();const search=new URLSearchParams({window_days:windowDays,limit:'3'});if(query.rating!=='all')search.set('rating',query.rating);read('/api/v1/projects/milestones?'+search,abort.signal).then(data=>{if(!abort.signal.aborted){setEvents(data.items.map((p:Home)=>({...p,completion:null})));setAsOf(data.as_of_date);}}).catch(e=>{if(!abort.signal.aborted)setError(e);});return()=>abort.abort();},[query.rating,windowDays,version]);
  useEffect(()=>{const abort=new AbortController();const search=new URLSearchParams({view:'home-v1',collection:'completed',limit:'9'});const cursor=completedCursors.current[completedIndex-1];if(cursor)search.set('cursor',cursor);read('/api/v1/projects?'+search,abort.signal).then(data=>{if(!abort.signal.aborted){setCompleted(data);setCompletedLoaded(completedIndex);completedCursors.current[completedIndex]=data.next_cursor;}}).catch(e=>{if(!abort.signal.aborted)setError(e);});return()=>abort.abort();},[completedIndex,version]);
  useEffect(()=>{const abort=new AbortController();const search=new URLSearchParams({view:'home-v1',collection:'other',limit:'9'});const cursor=otherCursors.current[otherIndex-1];if(cursor)search.set('cursor',cursor);read('/api/v1/projects?'+search,abort.signal).then(data=>{if(!abort.signal.aborted){setOther(data);setOtherLoaded(otherIndex);otherCursors.current[otherIndex]=data.next_cursor;}}).catch(e=>{if(!abort.signal.aborted)setError(e);});return()=>abort.abort();},[otherIndex,version]);
  function change(next:Partial<MainQuery>){mainCursors.current=[null];setPage(1);setQuery(q=>({...q,...next}));}
  function operationError(value:unknown,state:OperationResult['state']='failed'):OperationResult{const error=publicError(value);return {state,request_id:error.request_id,error};}
  async function reconcile():Promise<OperationResult>{
    const saved=pending.current;if(!saved)return {state:'failed',request_id:null,error:{code:'NOT_FOUND',message:'没有待核对的原操作',retryable:false,request_id:null}};
    try{const search=new URLSearchParams({method:saved.method,path:saved.path,contract:saved.contract});await read('/api/v1/projects/operations/'+saved.key+'?'+search);persist(null);reload();return {state:'succeeded',request_id:null};}catch(e){const error=e as PublicError;return {state:'unknown',request_id:error.request_id,error:{...error,message:error.code==='NOT_FOUND'?'尚未找到原操作回执；结果仍待核对，请勿重复提交':error.message}};}
  }
  async function write(path:string,method:string,body:unknown,target?:ProjectRef,home=true):Promise<OperationResult>{
    if(pending.current){const checked=await reconcile();return checked.state==='succeeded'?operationError({error:{code:'CONFLICT',message:'原操作已核对完成，请重新检查资料后提交当前操作'}}):checked;}
    const saved={key:crypto.randomUUID(),path,method,contract:home?'projects-home-v1':'phase2-v1.0.0'};persist(saved);
    try{const response=await fetch(path+(home?'?view=home-v1':''),{method,headers:{'content-type':'application/json','x-csrf-token':csrf,'idempotency-key':saved.key,...(target?{'if-match':`"rev-${target.revision}"`}:{})},...(method==='DELETE'?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(10000)});const value=await response.json();
      if(!response.ok){if(response.status<500){persist(null);if(response.status===409)reload();}return operationError(value,response.status>=500?'unknown':'failed');}
      persist(null);mainCursors.current=[null];completedCursors.current=[null];otherCursors.current=[null];setPage(1);setCompletedIndex(1);setOtherIndex(1);setDetail(null);reload();return {state:'succeeded',request_id:value.request_id};
    }catch{return operationError({error:{code:'UPSTREAM_TIMEOUT',message:'写入结果待核对，保留原幂等键'},request_id:null},'unknown');}
  }
  async function openDetail(id:string){try{setDetail(await read('/api/v1/projects/'+id+'?view=home-v1'));}catch(e){setError(e as PublicError);}}
  const latest=new Map<string,Home>();
  for(const home of [...main.items,...completed.items,...other.items,...events,...(detail?[detail]:[])]){const previous=latest.get(home.project.project_id);if(!previous||home.project.revision>=previous.project.revision)latest.set(home.project.project_id,home);}
  const homes=[...latest.values()];
  const data:HomepageData={status:error?'error':loading&&!homes.length?'loading':homes.length?'ready':'empty',items:homes.map(p=>p.project),next_cursor:null,refreshing:loading,error};
  const pagination=(index:number,loaded:number,total:number,next:string|null,cursors:(string|null)[],move:(index:number)=>void)=><div className="hpv2-pagination"><Button size="sm" aria-label="上一页记录" disabled={index<=1||index!==loaded} onClick={()=>move(index-1)}>‹</Button><span>{index} / {Math.max(1,Math.ceil(total/9))} · {total}</span><Button size="sm" aria-label="下一页记录" disabled={!next||index!==loaded} onClick={()=>{if(index<cursors.length)move(index+1);}}>›</Button></div>;
  const draftBody=(draft:EditorDraft)=>({fields:draft.fields,milestone:draft.milestone,complete:draft.archive_after_save});
  return <ReferenceHomepage context={context} data={data} milestones={homes.map(p=>({...p.milestone,project_id:p.project.project_id}))} archiveNotes={homes.flatMap(p=>p.completion?[{project_id:p.project.project_id,previous_stage:p.completion.previous_stage,completed_on:p.completion.completed_at}]:[])} asOfDate={asOf}
    callbacks={{onCreateDraft:draft=>write('/api/v1/projects','POST',draftBody(draft)),onUpdateDraft:(target,draft)=>write('/api/v1/projects/'+target.project_id,'PATCH',{fields:draft.fields,milestone:draft.milestone,...(draft.archive_after_save?{complete:true}:{})},target),
      onDelete:target=>write('/api/v1/projects/'+target.project_id,'DELETE',{},target),onMembership:(target,action)=>write('/api/v1/projects/'+target.project_id+'/home-membership','POST',{action},target),
      onArchive:targets=>write('/api/v1/projects/completions','POST',{items:targets.map(t=>({project_id:t.project_id,revision:t.revision}))}),onRestore:target=>write('/api/v1/projects/'+target.project_id+'/restore','POST',{},target),onReconcile:reconcile,
      onQueryChange:(q:HomepageQuery)=>change({q:q.q,rating:q.rating,progress_stage:q.progress_stage}),onDiscoveryDateChange:day=>change({discovered_on:day??''}),onReload:reload}}
    server={{mainIds:main.items.map(p=>p.project.project_id),completedIds:completed.items.map(p=>p.project.project_id),otherIds:other.items.map(p=>p.project.project_id),eventIds:events.map(p=>p.project.project_id),total:main.total,page,hasNext:!!main.next_cursor,summary,
      onSort:value=>change({sort:value.key,direction:value.direction}),onPage:next=>{if(next>=1&&next<=mainCursors.current.length&&next<=page+1)setPage(next);},onWindow:setWindow,onDetail:id=>void openDetail(id),
      completedPagination:pagination(completedIndex,completedLoaded,completed.total,completed.next_cursor,completedCursors.current,setCompletedIndex),otherPagination:pagination(otherIndex,otherLoaded,other.total,other.next_cursor,otherCursors.current,setOtherIndex)}}/>;
}
