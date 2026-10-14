'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import {Badge,Button,Input,Modal,Select,Textarea} from './ui-port';
import {ArrowUpDown,ArrowUpRight,Check,FlaskConical,Plus,Search,SquarePen,X} from './icons';
import {initialQuery,progressStages,ratings,SITE_SCOPE,type HomepageCallbacks,type HomepageContext,type HomepageData,type HomepageQuery,type OperationResult,type ProjectFieldsProjection,type ProjectRef,type ProjectView,type PublicError} from '../../features/homepage/types';
import {canEdit,membershipLabels,pickFields,safeRejectedError,stageLabels,toPageViews,validateFields} from '../../features/homepage/view-model';
import './phase2-homepage.css';

interface Props {context:HomepageContext;data:HomepageData;callbacks?:HomepageCallbacks;query?:HomepageQuery}
type Intent={kind:'create'|'edit'|'remove'|'delete'|'add';project?:ProjectView};
const unresolved=(result:OperationResult|null)=>!!result&&['accepted','pending','running','unknown'].includes(result.state);
const operationLabels={accepted:'已受理，等待结果',pending:'等待执行',running:'操作处理中',unknown:'结果待核实',succeeded:'操作已确认完成',failed:'操作未完成'} as const;
const emptyFields:ProjectFieldsProjection={name:'',rating:null,description:'',website_url:null,notes:'',category:null,progress_stage:'todo',progress_percent:null,token_date:null,token_date_status:'unconfirmed'};

function ErrorMessage({error}:{error:PublicError}){
  return <div className="hp2-alert error" role="alert"><strong>{error.message}</strong><span>{error.code}{error.request_id?` · 请求编号 ${error.request_id}`:''}</span></div>;
}
function OperationMessage({operation,onReconcile,busy}:{operation:OperationResult|null;onReconcile?:()=>void;busy:boolean}){
  if(!operation)return null;
  return <div className={`hp2-alert ${operation.state==='failed'?'error':operation.state==='succeeded'?'success':'warning'}`} role="status">
    <div><strong>{operationLabels[operation.state]}</strong>{operation.error&&<span>{operation.error.message} · {operation.error.code}</span>}
      {operation.request_id&&<small>请求编号 {operation.request_id}</small>}
      {unresolved(operation)&&<span>保留原操作记录，先核对结果。</span>}</div>
    {unresolved(operation)&&onReconcile&&<Button className="hp2-button" disabled={busy} onClick={onReconcile}>{busy?'正在核对…':'核对结果'}</Button>}
  </div>;
}
export default function Phase2Homepage({context,data,callbacks={},query:injectedQuery}:Props){
  const [localQuery,setQuery]=useState<HomepageQuery>(initialQuery);
  const query=injectedQuery||localQuery;
  const [sort,setSort]=useState<'rating'|'name'|'discovered'|'progress'>('rating');
  const [detail,setDetail]=useState<string|null>(null),[intent,setIntent]=useState<Intent|null>(null);
  const [busy,setBusy]=useState(false),[operation,setOperation]=useState<OperationResult|null>(null),[hint,setHint]=useState('');
  const inFlight=useRef(false),search=useRef<HTMLInputElement>(null);
  const epoch=useRef(0);
  const allowed=canEdit(context),blocked=busy||unresolved(operation);
  useEffect(()=>{if(!allowed){setIntent(null);}},[allowed]);
  useEffect(()=>{epoch.current++;inFlight.current=false;setBusy(false);setIntent(null);setDetail(null);setOperation(null);setHint('');setQuery(initialQuery);},[context.mode]);
  useEffect(()=>{const key=(event:KeyboardEvent)=>{
    if(event.key==='/'&&!document.querySelector('dialog[open]')&&!['INPUT','SELECT','TEXTAREA'].includes((event.target as HTMLElement).tagName)){event.preventDefault();search.current?.focus();}
    if(event.key==='Escape'&&document.activeElement===search.current)changeQuery({...query,q:''});
  };window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[query,callbacks.onQueryChange]);
  const projection=useMemo(()=>{
    try{return {views:toPageViews(data.items,context.mode),error:null};}
    catch{return {views:[] as ProjectView[],error:{code:'VALIDATION_ERROR',message:'项目展示数据不可用。',retryable:false,request_id:context.request_id||null}};}
  },[data.items,context.mode,context.request_id]);
  const views=useMemo(()=>projection.views.filter(view=>{
    const p=view.record;
    return p.home_membership===query.home_membership&&(query.rating==='all'||(query.rating==='unrated'?p.rating===null:p.rating===query.rating))&&
      (query.progress_stage==='all'||p.progress_stage===query.progress_stage)&&(!query.q.trim()||[p.name,p.description,p.notes,p.category||''].join(' ').toLowerCase().includes(query.q.trim().toLowerCase()));
  }).sort((a,b)=>{
    if(sort==='name')return a.record.name.localeCompare(b.record.name,'zh-CN');
    if(sort==='rating')return (a.record.rating===null?9:ratings.indexOf(a.record.rating))-(b.record.rating===null?9:ratings.indexOf(b.record.rating));
    if(sort==='progress')return (b.record.progress_percent??-1)-(a.record.progress_percent??-1);
    return (Date.parse(b.record.discovered_at||'')||0)-(Date.parse(a.record.discovered_at||'')||0);
  }),[projection,query,sort]);
  const current=projection.views.find(view=>view.key===detail);
  function changeQuery(next:HomepageQuery){setQuery(next);callbacks.onQueryChange?.(next);}
  function ref(project:ProjectView):ProjectRef{return {project_id:project.key,revision:project.record.revision};}
  function available(kind:Intent['kind']):boolean{
    return kind==='create'?!!callbacks.onCreate:kind==='edit'?!!callbacks.onUpdate:kind==='delete'?!!callbacks.onDelete:!!callbacks.onMembership;
  }
  function open(next:Intent){if(allowed&&!blocked&&available(next.kind)){setOperation(null);setIntent(next);}}
  async function run(action:()=>Promise<OperationResult>,onSuccess?:()=>void):Promise<boolean>{
    if(inFlight.current)return false;
    const issuedEpoch=epoch.current;
    inFlight.current=true;setBusy(true);
    try{
      const result=await action();
      if(issuedEpoch!==epoch.current)return false;
      if(!result||!Object.hasOwn(operationLabels,result.state))throw new Error('INVALID_CALLBACK_RESULT');
      setOperation(result);
      if(result.state==='succeeded'){onSuccess?.();return true;}return false;
    }catch{if(issuedEpoch===epoch.current)setOperation({state:'unknown',request_id:context.request_id||null,error:safeRejectedError(context.request_id||null)});return false;}
    finally{if(issuedEpoch===epoch.current){inFlight.current=false;setBusy(false);}}
  }
  async function reconcile(){if(operation&&callbacks.onReconcile)await run(()=>callbacks.onReconcile!(operation),()=>setIntent(null));}
  async function save(fields:ProjectFieldsProjection):Promise<boolean>{
    if(!allowed||blocked||!intent)return false;
    const payload=pickFields(fields);
    if(intent.kind==='create'&&callbacks.onCreate)return run(()=>callbacks.onCreate!(payload),()=>setIntent(null));
    if(intent.kind==='edit'&&intent.project&&callbacks.onUpdate)return run(()=>callbacks.onUpdate!(ref(intent.project!),payload),()=>setIntent(null));
    return false;
  }
  async function confirm(){
    if(!allowed||blocked||!intent?.project)return;
    if(intent.kind==='delete'&&callbacks.onDelete)await run(()=>callbacks.onDelete!(ref(intent.project!)),()=>{setIntent(null);setDetail(null);});
    else if(callbacks.onMembership)await run(()=>callbacks.onMembership!(ref(intent.project!),intent.kind==='add'?'add':'remove'),()=>{setIntent(null);setDetail(null);});
  }
  const error=projection.error||data.error;
  const initialLoading=data.status==='loading'&&!data.items.length;
  const filtered=!!query.q||query.rating!=='all'||query.progress_stage!=='all';
  const actionTitle=(kind:Intent['kind'])=>!allowed?'只读：没有项目编辑能力':blocked?'先核对当前操作结果':!available(kind)?'此操作回调尚未接入':undefined;
  return <div className="hp2-root" data-mode={context.mode}>
    <a className="hp2-skip" href="#hp2-projects">跳到项目列表</a>
    <div className={`hp2-mode ${context.mode}`}><FlaskConical size={14}/><strong>{context.mode==='demo'?'演示数据':'Live 数据模式'}</strong><span>{context.mode==='demo'?'虚构项目与模拟结果，仅用于测试界面。':'数据和操作结果由调用方提供。'}</span><span className="hp2-scope">{SITE_SCOPE} · {allowed?'可编辑':'只读'}</span></div>
    <header className="hp2-heading"><div><small>IKUN.CA / MY PROJECTS</small><h1>正在做的项目</h1><p>研究、进度与下一步行动，集中在同一张表里。</p></div><Button className="hp2-button primary" title={actionTitle('create')} disabled={!allowed||blocked||!callbacks.onCreate} onClick={()=>open({kind:'create'})}><Plus size={16}/>添加项目</Button></header>
    {!intent&&<OperationMessage operation={operation} onReconcile={callbacks.onReconcile?reconcile:undefined} busy={busy}/>}
    {hint&&<div className="hp2-hint" role="status">{hint}<Button aria-label="关闭提示" onClick={()=>setHint('')}><X size={13}/></Button></div>}
    <section className="hp2-panel" id="hp2-projects" aria-label="项目工作列表">
      <div className="hp2-tabs" role="tablist" aria-label="主页成员范围">{(['active','hidden','removed'] as const).map(value=><Button key={value} role="tab" aria-selected={query.home_membership===value} onClick={()=>changeQuery({...query,home_membership:value})}>{membershipLabels[value]}<span>{projection.views.filter(view=>view.record.home_membership===value).length}</span></Button>)}<span className="hp2-page-note">当前页 · 最多 100 条</span></div>
      <div className="hp2-toolbar"><div className="hp2-search"><Search size={15}/><Input ref={search} value={query.q} aria-label="搜索项目" placeholder="搜索名称、简介、备注…" onChange={event=>changeQuery({...query,q:event.target.value})}/>{query.q?<Button aria-label="清空搜索" onClick={()=>changeQuery({...query,q:''})}><X size={13}/></Button>:<kbd>/</kbd>}</div>
        <Select aria-label="评分筛选" value={query.rating} onChange={event=>changeQuery({...query,rating:event.target.value as HomepageQuery['rating']})}><option value="all">全部评分</option>{ratings.map(rating=><option key={rating}>{rating}</option>)}<option value="unrated">未评分</option></Select>
        <Select aria-label="进度筛选" value={query.progress_stage} onChange={event=>changeQuery({...query,progress_stage:event.target.value as HomepageQuery['progress_stage']})}><option value="all">全部进度</option>{progressStages.map(stage=><option value={stage} key={stage}>{stageLabels[stage]}</option>)}</Select>
        {filtered&&<Button className="hp2-text-button" onClick={()=>changeQuery({...initialQuery,home_membership:query.home_membership})}>清除筛选</Button>}
        <label className="hp2-sort"><ArrowUpDown size={13}/><Select aria-label="当前页排序" value={sort} onChange={event=>setSort(event.target.value as typeof sort)}><option value="rating">评分优先</option><option value="discovered">最新发现</option><option value="name">名称排序</option><option value="progress">进度排序</option></Select></label>
        <Button className="hp2-button" disabled={!callbacks.onReload||data.refreshing||busy} title={!callbacks.onReload?'刷新回调尚未接入':undefined} onClick={callbacks.onReload}>{data.refreshing?'刷新中…':'刷新'}</Button>
      </div>
      {error&&<div className="hp2-error-row"><ErrorMessage error={error}/>{callbacks.onReload&&<Button className="hp2-button" disabled={!!data.refreshing} onClick={callbacks.onReload}>重新读取</Button>}</div>}
      {data.refreshing&&<div className="hp2-refreshing" role="status">正在刷新，保留已加载的项目和当前筛选。</div>}
      <div className="hp2-table-scroll" tabIndex={0} aria-label="项目表格，可横向滚动" aria-busy={initialLoading||!!data.refreshing}>
        <table className="hp2-table"><colgroup><col style={{width:200}}/><col style={{width:66}}/><col style={{width:150}}/><col style={{width:128}}/><col style={{width:'23%'}}/><col style={{width:122}}/><col style={{width:130}}/><col/><col style={{width:104}}/></colgroup>
          <thead><tr>{['项目名称','评分','发现时间 · 北京','官网','简介','进度','发币日期','备注 / 下一步','操作'].map(label=><th key={label}>{label}</th>)}</tr></thead>
          <tbody>{views.map(view=><tr key={view.key} data-project-id={view.key}><td><Button className="hp2-project-name" onClick={()=>setDetail(view.key)}><span className="hp2-avatar">{view.record.name.slice(0,1)}</span><span><strong>{view.record.name}</strong><small>{view.record.category||'未分类'}{context.mode==='demo'&&<em>演示</em>}</small></span></Button></td>
            <td><Badge className={`hp2-rating rating-${view.record.rating||'none'}`}>{view.record.rating||'未评分'}</Badge></td><td className="hp2-date">{view.discoveredLabel}</td>
            <td>{view.website?<a href={view.website} target="_blank" rel="noopener noreferrer" className="hp2-website" onClick={event=>{if(new URL(view.website!).hostname.endsWith('.example')){event.preventDefault();setHint('演示官网占位地址，不打开真实项目。');}}}><span>{new URL(view.website).hostname}</span><ArrowUpRight size={12}/></a>:<span className="hp2-muted">未提供</span>}</td>
            <td><span className="hp2-cell-copy" title={view.record.description}>{view.record.description||'—'}</span></td><td><div className="hp2-progress"><span>{view.progressLabel}</span><small>{view.percentLabel}</small>{view.record.progress_percent!==null&&<div><i style={{width:`${view.record.progress_percent}%`}}/></div>}</div></td><td className="hp2-date">{view.tokenLabel}</td><td><span className="hp2-cell-copy" title={view.record.notes}>{view.record.notes||'—'}</span></td>
            <td><div className="hp2-actions"><Button className="hp2-icon-button" aria-label={`编辑 ${view.record.name}`} disabled={!allowed||blocked||!callbacks.onUpdate} title={actionTitle('edit')} onClick={()=>open({kind:'edit',project:view})}><SquarePen size={15}/></Button><Button className="hp2-text-button" disabled={!allowed||blocked||!callbacks.onMembership} title={actionTitle(view.record.home_membership==='active'?'remove':'add')} onClick={()=>open({kind:view.record.home_membership==='active'?'remove':'add',project:view})}>{view.record.home_membership==='active'?'移除':'加入'}</Button></div></td></tr>)}</tbody>
        </table>
        {initialLoading?<div className="hp2-skeleton" role="status" aria-label="正在加载项目">{Array.from({length:6},(_,i)=><span key={i}/>)}</div>:!views.length&&!error?<div className="hp2-empty"><h2>{filtered?'没有匹配的项目':query.home_membership==='removed'?'暂无已移除项目':query.home_membership==='hidden'?'暂无未加入主页的项目':'主页还没有项目'}</h2><p>{filtered?'调整筛选或清除关键词。':'项目资料由调用方提供；当前列表为空。'}</p></div>:null}
      </div><div className="hp2-table-footer"><span>当前页显示 {views.length} / {data.items.length} 个项目 · 排序仅作用于本页</span><span>{data.next_cursor?<Button className="hp2-button" disabled={!callbacks.onNextPage||!!data.refreshing} title={!callbacks.onNextPage?'分页回调尚未接入':undefined} onClick={()=>callbacks.onNextPage?.(data.next_cursor!)}>下一页</Button>:'没有更多结果'}</span></div>
    </section>
    {current&&!intent&&<Modal title="项目资料" close={()=>setDetail(null)}><div className="hp2-dialog-body"><div className="hp2-detail-heading"><h2>{current.record.name}</h2><Badge className="hp2-rating">{current.record.rating||'未评分'}</Badge></div><dl className="hp2-detail-meta"><div><dt>主页状态</dt><dd>{membershipLabels[current.record.home_membership]}</dd></div><div><dt>发现时间</dt><dd>{current.discoveredLabel}</dd></div><div><dt>进度</dt><dd>{current.progressLabel} · {current.percentLabel}</dd></div><div><dt>发币日期</dt><dd>{current.tokenLabel}</dd></div><div><dt>官网</dt><dd>{current.website||'未提供'}</dd></div><div><dt>项目 ID</dt><dd>{current.key}</dd></div><div><dt>版本</dt><dd>{current.record.revision}</dd></div></dl><h3>简介</h3><p>{current.record.description||'尚未填写。'}</p><h3>备注 / 下一步</h3><p className="hp2-notes">{current.record.notes||'尚未填写。'}</p>{context.mode==='demo'&&<small className="hp2-disclosure">虚构演示项目，不是研究或监控结果。</small>}<div className="hp2-dialog-footer"><Button className="hp2-button" disabled={!allowed||blocked||!callbacks.onDelete} title={actionTitle('delete')} onClick={()=>open({kind:'delete',project:current})}>删除主页条目</Button><Button className="hp2-button primary" disabled={!allowed||blocked||!callbacks.onUpdate} title={actionTitle('edit')} onClick={()=>open({kind:'edit',project:current})}>编辑资料</Button></div></div></Modal>}
    {intent&&(intent.kind==='create'||intent.kind==='edit')&&<ProjectForm item={intent.project} mode={context.mode} pending={busy} unsettled={unresolved(operation)} blocked={blocked||operation?.error?.code==='VERSION_CONFLICT'} close={()=>{if(!busy)setIntent(null);}} save={save}><OperationMessage operation={operation} onReconcile={callbacks.onReconcile?reconcile:undefined} busy={busy}/>{operation?.error?.code==='VERSION_CONFLICT'&&<div className="hp2-immutable">关闭窗口并重新读取最新资料后，再决定是否提交。</div>}</ProjectForm>}
    {intent&&!['create','edit'].includes(intent.kind)&&<Modal title={intent.kind==='add'?'加入主页':intent.kind==='delete'?'删除主页条目':'从主页移除'} pending={busy} close={()=>{if(!busy)setIntent(null);}}><div className="hp2-dialog-body"><h2>{intent.project?.record.name}</h2><p>{intent.kind==='add'?'明确加入主页，保留当前进度和项目资料。':'仅移出主页。项目资料、canonical ID、审计和监控引用保留，监控状态保持原样。'}</p><OperationMessage operation={operation} onReconcile={callbacks.onReconcile?reconcile:undefined} busy={busy}/><div className="hp2-dialog-footer"><Button className="hp2-button" data-initial-focus disabled={busy} onClick={()=>setIntent(null)}>取消</Button><Button className={`hp2-button ${intent.kind==='add'?'primary':'danger'}`} disabled={blocked||!allowed} onClick={confirm}>{busy?'提交中…':intent.kind==='add'?'确认加入':'确认移除主页'}</Button></div></div></Modal>}
  </div>;
}

function ProjectForm({item,mode,pending,unsettled,blocked,close,save,children}:{item?:ProjectView;mode:HomepageContext['mode'];pending:boolean;unsettled:boolean;blocked:boolean;close:()=>void;save:(fields:ProjectFieldsProjection)=>Promise<boolean>;children:React.ReactNode}){
  const [initial]=useState(()=>item?pickFields(item.record):emptyFields);
  const [fields,setFields]=useState<ProjectFieldsProjection>(initial),[error,setError]=useState(''),[discard,setDiscard]=useState(false);
  const dirty=JSON.stringify(initial)!==JSON.stringify(fields);
  const exit=()=>{if(pending)return;if(dirty&&!unsettled)setDiscard(true);else close();};
  function update<K extends keyof ProjectFieldsProjection>(key:K,value:ProjectFieldsProjection[K]){setFields(previous=>({...previous,[key]:value}));setError('');}
  async function submit(event:React.FormEvent){event.preventDefault();if(blocked)return;const payload={...pickFields(fields),name:fields.name.trim()};const invalid=validateFields(payload);if(invalid){setError(invalid);return;}await save(payload);}
  return <Modal title={item?'编辑项目资料':'添加项目'} pending={pending} close={discard?()=>setDiscard(false):exit}>{discard?<div className="hp2-dialog-body"><h2>放弃未保存的修改？</h2><div className="hp2-dialog-footer"><Button className="hp2-button" data-initial-focus autoFocus onClick={()=>setDiscard(false)}>继续编辑</Button><Button className="hp2-button danger" onClick={close}>放弃修改</Button></div></div>:<form className="hp2-form" onSubmit={submit}>
    <div className="hp2-form-note">{mode==='demo'?'演示编辑 · 操作由模拟回调处理':'操作由接入方回调处理，服务端仍需验证权限与版本。'}</div>
    <div className="hp2-form-grid"><label>项目名称<Input data-initial-focus required maxLength={120} value={fields.name} disabled={blocked} onChange={event=>update('name',event.target.value)}/></label><label>评分<Select aria-label="评分" disabled={blocked} value={fields.rating||''} onChange={event=>update('rating',event.target.value?event.target.value as ProjectFieldsProjection['rating']:null)}><option value="">未评分</option>{ratings.map(rating=><option key={rating}>{rating}</option>)}</Select></label>
      <label>分类<Input maxLength={80} value={fields.category||''} disabled={blocked} onChange={event=>update('category',event.target.value||null)}/></label><label>官网<Input type="url" value={fields.website_url||''} disabled={blocked} onChange={event=>update('website_url',event.target.value||null)} placeholder="https://"/></label>
      <label>进度阶段<Select aria-label="进度阶段" value={fields.progress_stage} disabled={blocked} onChange={event=>update('progress_stage',event.target.value as ProjectFieldsProjection['progress_stage'])}>{progressStages.map(stage=><option value={stage} key={stage}>{stageLabels[stage]}</option>)}</Select></label><label>进度百分比（未知留空）<Input type="number" min={0} max={100} value={fields.progress_percent??''} disabled={blocked} onChange={event=>update('progress_percent',event.target.value===''?null:event.target.valueAsNumber)}/></label>
      <label>发币日期<Input type="date" value={fields.token_date||''} disabled={blocked} onChange={event=>setFields(previous=>({...previous,token_date:event.target.value||null,token_date_status:event.target.value?(previous.token_date_status==='unconfirmed'?'estimated':previous.token_date_status):'unconfirmed'}))}/></label><label>日期状态<Select aria-label="日期状态" value={fields.token_date_status} disabled={blocked||!fields.token_date} onChange={event=>update('token_date_status',event.target.value as ProjectFieldsProjection['token_date_status'])}>{fields.token_date?<><option value="estimated">预计</option><option value="confirmed">已确认</option></>:<option value="unconfirmed">未确认</option>}</Select></label></div>
    {item&&<div className="hp2-immutable">发现时间和服务端 ID/时间只读；版本 {item.record.revision}。</div>}
    <label>项目简介<Textarea aria-label="项目简介" rows={3} maxLength={4000} disabled={blocked} value={fields.description} onChange={event=>update('description',event.target.value)}/></label><label>备注 / 下一步<Textarea aria-label="备注 / 下一步" rows={3} maxLength={4000} disabled={blocked} value={fields.notes} onChange={event=>update('notes',event.target.value)}/></label>
    {error&&<div className="hp2-alert error" role="alert">{error}</div>}{children}<div className="hp2-dialog-footer"><Button className="hp2-button" disabled={pending} onClick={exit}>{blocked&&!pending?'关闭':'取消'}</Button><Button type="submit" className="hp2-button primary" disabled={blocked}><Check size={14}/>{pending?'提交中…':item?'保存修改':'添加项目'}</Button></div>
  </form>}</Modal>;
}
