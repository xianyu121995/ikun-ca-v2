'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import {Alert,Badge,Button,DataTable,EmptyState,ErrorState,Icon,Input,PageHeader,Panel,ScoreBadge,SearchInput,Select,Toolbar,type TableColumn,type TableSort} from '@ikun/ui';
import {HomepageDialog as Modal} from './shared-dialog';
import {Plus,SquarePen} from './icons';
import {initialQuery,progressStages,ratings,SITE_SCOPE,type HomepageCallbacks,type HomepageContext,type HomepageData,type HomepageQuery,type OperationResult,type ProjectFieldsProjection,type ProjectRef,type ProjectView,type PublicError} from '../../features/homepage/types';
import {canEdit,membershipLabels,pickFields,safeRejectedError,stageLabels,toPageViews,validateFields} from '../../features/homepage/view-model';
import './phase2-homepage.css';

interface Props {context:HomepageContext;data:HomepageData;callbacks?:HomepageCallbacks;query?:HomepageQuery}
type Intent={kind:'create'|'edit'|'remove'|'delete'|'add';project?:ProjectView};
const unresolved=(result:OperationResult|null)=>!!result&&['accepted','pending','running','unknown'].includes(result.state);
const operationLabels={accepted:'已受理，等待结果',pending:'等待执行',running:'操作处理中',unknown:'结果待核实',succeeded:'操作已确认完成',failed:'操作未完成'} as const;
const emptyFields:ProjectFieldsProjection={name:'',rating:null,description:'',website_url:null,notes:'',category:null,progress_stage:'todo',progress_percent:null,token_date:null,token_date_status:'unconfirmed'};

function ErrorMessage({error}:{error:PublicError}){
  return <ErrorState title={error.message} description="请核对公开错误信息。已加载的项目仍可查看。" code={error.code} requestId={error.request_id||undefined}/>;
}
function OperationMessage({operation,onReconcile,busy}:{operation:OperationResult|null;onReconcile?:()=>void;busy:boolean}){
  if(!operation)return null;
  return <Alert tone={operation.state==='failed'?'danger':operation.state==='succeeded'?'success':'warning'} title={operationLabels[operation.state]} requestId={operation.request_id||undefined} code={operation.error?.code}
    action={unresolved(operation)&&onReconcile?<Button size="sm" pending={busy} onClick={onReconcile}>{busy?'正在核对…':'核对结果'}</Button>:undefined}>
    {operation.error&&<p>{operation.error.message}</p>}{unresolved(operation)&&<p>保留原操作记录，先核对结果。</p>}
  </Alert>;
}
export default function Phase2Homepage({context,data,callbacks={},query:injectedQuery}:Props){
  const [localQuery,setQuery]=useState<HomepageQuery>(initialQuery);
  const query=injectedQuery||localQuery;
  const [sort,setSort]=useState<TableSort>({key:'rating',direction:'asc'});
  const [detail,setDetail]=useState<string|null>(null),[intent,setIntent]=useState<Intent|null>(null);
  const [busy,setBusy]=useState(false),[operation,setOperation]=useState<OperationResult|null>(null),[hint,setHint]=useState(''),[timelineOpen,setTimelineOpen]=useState(false);
  const inFlight=useRef(false),search=useRef<HTMLDivElement>(null);
  const epoch=useRef(0);
  const allowed=canEdit(context),blocked=busy||unresolved(operation);
  useEffect(()=>{if(!allowed){setIntent(null);}},[allowed]);
  useEffect(()=>{epoch.current++;inFlight.current=false;setBusy(false);setIntent(null);setDetail(null);setOperation(null);setHint('');setTimelineOpen(false);setQuery(initialQuery);},[context.mode]);
  useEffect(()=>{const key=(event:KeyboardEvent)=>{
    if(((event.key==='/'&&!['INPUT','SELECT','TEXTAREA'].includes((event.target as HTMLElement).tagName))||((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'))&&!document.querySelector('dialog[open]')){event.preventDefault();search.current?.querySelector('input')?.focus();}
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
    let comparison=0;
    if(sort.key==='name')comparison=a.record.name.localeCompare(b.record.name,'zh-CN');
    else {
      const value=(view:ProjectView):number|null=>sort.key==='rating'?(view.record.rating===null?null:ratings.indexOf(view.record.rating)):sort.key==='progress'?view.record.progress_percent:view.record.discovered_at===null?null:Date.parse(view.record.discovered_at);
      const left=value(a),right=value(b);
      // Unknown values always stay last, including when the direction changes.
      if(left===null||right===null)return left===right?a.key.localeCompare(b.key):left===null?1:-1;
      comparison=left-right;
    }
    return (sort.direction==='asc'?comparison:-comparison)||a.key.localeCompare(b.key);
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
  const columns:TableColumn<ProjectView>[]=[
    {key:'rating',header:'评分',sortable:true,width:'78px',render:view=><ScoreBadge grade={view.record.rating}/>},
    {key:'discovered',header:'发现时间 · 北京',sortable:true,width:'132px',render:view=><span className="hp2-date">{view.discoveredLabel}</span>},
    {key:'name',header:'项目名称',sortable:true,width:'200px',render:view=><Button variant="ghost" className="hp2-project-name" data-project-id={view.key} onClick={()=>setDetail(view.key)}><span className="hp2-avatar">{view.record.name.slice(0,1)}</span><span><strong>{view.record.name}</strong><small>{view.record.category||'未分类'}{context.mode==='demo'&&<em>演示</em>}</small></span></Button>},
    {key:'website',header:'官网',width:'165px',render:view=>view.website?<a href={view.website} target="_blank" rel="noopener noreferrer" className="hp2-website" onClick={event=>{if(new URL(view.website!).hostname.endsWith('.example')){event.preventDefault();setHint('演示官网占位地址，不打开真实项目。');}}}><span>{new URL(view.website).hostname}</span><Icon name="arrow" width={12} height={12}/></a>:<span className="hp2-muted">未提供</span>},
    {key:'description',header:'简介',width:'22%',render:view=><span className="hp2-cell-copy" title={view.record.description}>{view.record.description||'—'}</span>},
    {key:'progress',header:'进度',sortable:true,width:'122px',render:view=><div className="hp2-progress"><Badge tone={view.record.progress_stage==='participating'||view.record.progress_stage==='completed'?'success':view.record.progress_stage==='paused'?'neutral':'info'}>{view.progressLabel}</Badge><small>{view.percentLabel}</small>{view.record.progress_percent!==null&&<div><i style={{width:`${view.record.progress_percent}%`}}/></div>}</div>},
    {key:'token_date',header:'发币日期',width:'145px',render:view=><span className="hp2-date">{view.tokenLabel}</span>},
    {key:'notes',header:'备注 / 下一步',render:view=><span className="hp2-cell-copy" title={view.record.notes}>{view.record.notes||'—'}</span>},
    {key:'actions',header:'操作',width:'118px',render:view=><div className="hp2-actions"><Button variant="ghost" size="sm" className="hp2-icon-button" aria-label={`查看 ${view.record.name}`} onClick={()=>setDetail(view.key)}><Icon name="eye" width={16} height={16}/></Button><Button variant="ghost" size="sm" className="hp2-icon-button" aria-label={`编辑 ${view.record.name}`} disabled={!allowed||blocked||!callbacks.onUpdate} title={actionTitle('edit')} onClick={()=>open({kind:'edit',project:view})}><SquarePen size={15}/></Button><Button variant="ghost" size="sm" className="hp2-text-button" disabled={!allowed||blocked||!callbacks.onMembership} title={actionTitle(view.record.home_membership==='active'?'remove':'add')} onClick={()=>open({kind:view.record.home_membership==='active'?'remove':'add',project:view})}>{view.record.home_membership==='active'?'移除':'加入'}</Button></div>},
  ];
  const emptyTitle=filtered?'没有匹配的项目':query.home_membership==='removed'?'暂无已移除项目':query.home_membership==='hidden'?'暂无未加入主页的项目':'主页还没有项目';
  const homeProjects=projection.views.filter(view=>view.record.home_membership==='active');
  const memberProjects=projection.views.filter(view=>view.record.home_membership===query.home_membership);
  const datedProjects=homeProjects.filter(view=>view.record.token_date!==null).sort((a,b)=>a.record.token_date!.localeCompare(b.record.token_date!)||a.key.localeCompare(b.key));
  const summary=[
    {label:'项目总数',count:homeProjects.length,detail:'主页正在做',icon:<Icon name="layers"/>,tone:'all',action:()=>changeQuery(initialQuery)},
    ...(['S','A','B'] as const).map(grade=>({label:`${grade} 级项目`,count:homeProjects.filter(view=>view.record.rating===grade).length,detail:grade==='S'?'重点关注':grade==='A'?'优先研究':'持续观察',icon:<span>{grade}</span>,tone:grade,action:()=>changeQuery({...initialQuery,rating:grade})})),
    {label:'参与中',count:homeProjects.filter(view=>view.record.progress_stage==='participating').length,detail:'按已填写阶段',icon:<Icon name="radar"/>,tone:'active',action:()=>changeQuery({...initialQuery,progress_stage:'participating'})},
    {label:'已暂停',count:homeProjects.filter(view=>view.record.progress_stage==='paused').length,detail:'暂时观察',icon:<span>Ⅱ</span>,tone:'paused',action:()=>changeQuery({...initialQuery,progress_stage:'paused'})},
  ];
  return <div className="hp2-root ik-theme" data-mode={context.mode}>
    <div className={`hp2-mode ${context.mode}`}><Icon name="warning" width={14} height={14}/><strong>{context.mode==='demo'?'演示数据':'Live 数据模式'}</strong><span>{context.mode==='demo'?'虚构项目与模拟结果，仅用于测试界面。':'数据和操作结果由调用方提供。'}</span><span className="hp2-scope">{SITE_SCOPE} · {allowed?'可编辑':'只读'}</span></div>
    <PageHeader title="我正在做的项目" description="跟踪正在研究的项目，记录进度，掌握每一个重要节点。" actions={<><div ref={search} className="hp2-search-slot"><SearchInput label="搜索项目" value={query.q} placeholder="搜索项目名称、分类、备注…" onValueChange={q=>changeQuery({...query,q})}/>{!query.q&&<kbd>⌘ K</kbd>}</div><Button variant="primary" title={actionTitle('create')} disabled={!allowed||blocked||!callbacks.onCreate} onClick={()=>open({kind:'create'})} icon={<Plus size={16}/>}>添加项目</Button></>}/>
    <section className="hp2-overview" aria-label="项目概览">
      {summary.map(card=><Panel key={card.label} className={`hp2-stat hp2-stat-${card.tone}`}><Button variant="ghost" className="hp2-stat-button" aria-label={`${card.label} ${card.count} 个，筛选项目`} onClick={card.action}><span className="hp2-stat-icon">{card.icon}</span><span className="hp2-stat-copy"><span>{card.label}</span><strong>{initialLoading?'—':card.count}<small> 个</small></strong><small>{card.detail}</small></span></Button></Panel>)}
      <span className="hp2-overview-scope">统计范围：当前页已加载的主页项目</span>
    </section>
    <Panel className="hp2-timeline" title={<span className="hp2-section-title">近期重要时间</span>} description="当前页已填写的发币节点，预计日期仍待确认。" actions={<Button variant="ghost" size="sm" disabled={initialLoading||!datedProjects.length} onClick={()=>setTimelineOpen(true)}>查看全部 <Icon name="arrow" width={15} height={15}/></Button>}>
      {initialLoading?<p className="hp2-muted">正在加载项目时间…</p>:datedProjects.length?<div className="hp2-date-grid">{datedProjects.slice(0,4).map(view=><Button variant="ghost" key={view.key} className="hp2-date-card" onClick={()=>setDetail(view.key)}><span className="hp2-avatar">{view.record.name.slice(0,1)}</span><span className="hp2-date-name"><strong>{view.record.name}</strong><small>{view.record.token_date_status==='estimated'?'预计发币':'已确认发币'}{context.mode==='demo'?' · 演示':''}</small></span><span className="hp2-date-value"><strong>{view.record.token_date}</strong><Badge tone={view.record.token_date_status==='estimated'?'warning':'info'}>{view.record.token_date_status==='estimated'?'预计':'已确认'}</Badge></span></Button>)}</div>:<p className="hp2-muted">暂无已填写的项目时间，未知日期保持未确认。</p>}
    </Panel>
    {!allowed&&<p className="hp2-readonly">当前账号只读，可搜索、筛选和查看项目资料。</p>}
    {!intent&&<OperationMessage operation={operation} onReconcile={callbacks.onReconcile?reconcile:undefined} busy={busy}/>}
    {hint&&<Alert tone="info" title={hint} action={<Button variant="ghost" size="sm" aria-label="关闭提示" onClick={()=>setHint('')}><Icon name="close" width={13} height={13}/></Button>}/>}
    <Panel className="ik-panel--table hp2-panel" id="hp2-projects" aria-label="项目工作列表">
      <div className="hp2-list-heading"><div><h2 className="hp2-section-title">持续跟踪项目表</h2><p>{context.mode==='demo'?'演示数据 / UI 原型':'项目资料与进度'} · 当前页</p></div><div className="hp2-tabs" role="tablist" aria-label="主页成员范围">{(['active','hidden','removed'] as const).map(value=><Button variant="ghost" key={value} role="tab" aria-selected={query.home_membership===value} onClick={()=>changeQuery({...query,home_membership:value})}>{membershipLabels[value]}<span>{projection.views.filter(view=>view.record.home_membership===value).length}</span></Button>)}</div></div>
      <Toolbar className="hp2-toolbar"><div className="hp2-grade-filters" aria-label="评分快捷筛选">{(['all','S','A','B'] as const).map(grade=><Button key={grade} variant={query.rating===grade?'primary':'ghost'} size="sm" aria-pressed={query.rating===grade} onClick={()=>changeQuery({...query,rating:grade})}>{grade==='all'?'全部':`${grade}级`}<span>{grade==='all'?memberProjects.length:memberProjects.filter(view=>view.record.rating===grade).length}</span></Button>)}</div>
        <Select label="评分筛选" value={query.rating} onChange={event=>changeQuery({...query,rating:event.target.value as HomepageQuery['rating']})}><option value="all">全部评分</option>{ratings.map(rating=><option key={rating}>{rating}</option>)}<option value="unrated">未评分</option></Select>
        <Select label="进度筛选" value={query.progress_stage} onChange={event=>changeQuery({...query,progress_stage:event.target.value as HomepageQuery['progress_stage']})}><option value="all">全部进度</option>{progressStages.map(stage=><option value={stage} key={stage}>{stageLabels[stage]}</option>)}</Select>
        {filtered&&<Button variant="ghost" size="sm" onClick={()=>changeQuery({...initialQuery,home_membership:query.home_membership})}>清除筛选</Button>}
        <Select className="hp2-sort" label="当前页排序" value={`${sort.key}:${sort.direction}`} onChange={event=>{const [key,direction]=event.target.value.split(':');setSort({key:key!,direction:direction as TableSort['direction']});}}>
          <option value="rating:asc">评分 S → D</option><option value="rating:desc">评分 D → S</option><option value="discovered:desc">最新发现</option><option value="discovered:asc">最早发现</option><option value="name:asc">名称 A → Z</option><option value="name:desc">名称 Z → A</option><option value="progress:desc">进度高 → 低</option><option value="progress:asc">进度低 → 高</option>
        </Select>
        <Button size="sm" disabled={!callbacks.onReload||data.refreshing||busy} title={!callbacks.onReload?'刷新回调尚未接入':undefined} onClick={callbacks.onReload}>{data.refreshing?'刷新中…':'刷新'}</Button>
      </Toolbar>
      <DataTable caption="项目表格" columns={columns} rows={views} rowKey={view=>view.key} sort={sort} onSortChange={setSort} minWidth={1380} loading={initialLoading} refreshing={data.refreshing}
        error={error?<div className="hp2-error-row"><ErrorMessage error={error}/>{callbacks.onReload&&<Button size="sm" disabled={!!data.refreshing} onClick={callbacks.onReload}>重新读取</Button>}</div>:undefined}
        empty={<EmptyState title={emptyTitle} description={filtered?'调整筛选或清除关键词。':'项目资料由调用方提供；当前列表为空。'}/>}/>
      <div className="hp2-table-footer"><span>当前页显示 {views.length} / {data.items.length} 个项目 · 搜索、筛选与排序仅作用于本页</span><span>{data.next_cursor?<Button size="sm" disabled={!callbacks.onNextPage||!!data.refreshing} title={!callbacks.onNextPage?'分页回调尚未接入':undefined} onClick={()=>callbacks.onNextPage?.(data.next_cursor!)}>下一页</Button>:'没有更多结果'}</span></div>
    </Panel>
    {timelineOpen&&<Modal title="项目时间" close={()=>setTimelineOpen(false)}><div className="hp2-dialog-body"><p>当前页已填写的发币日期；预计时间不代表已确认事件。</p><div className="hp2-time-list">{datedProjects.map(view=><div key={view.key}><strong>{view.record.name}</strong><span>{view.tokenLabel}</span></div>)}</div></div></Modal>}
    {current&&!intent&&<Modal title="项目资料" close={()=>setDetail(null)}><div className="hp2-dialog-body"><div className="hp2-detail-heading"><h2>{current.record.name}</h2><ScoreBadge grade={current.record.rating}/></div><dl className="hp2-detail-meta"><div><dt>主页状态</dt><dd>{membershipLabels[current.record.home_membership]}</dd></div><div><dt>发现时间</dt><dd>{current.discoveredLabel}</dd></div><div><dt>进度</dt><dd>{current.progressLabel} · {current.percentLabel}</dd></div><div><dt>发币日期</dt><dd>{current.tokenLabel}</dd></div><div><dt>官网</dt><dd>{current.website||'未提供'}</dd></div><div><dt>项目 ID</dt><dd>{current.key}</dd></div><div><dt>版本</dt><dd>{current.record.revision}</dd></div></dl><h3>简介</h3><p>{current.record.description||'尚未填写。'}</p><h3>备注 / 下一步</h3><p className="hp2-notes">{current.record.notes||'尚未填写。'}</p>{context.mode==='demo'&&<small className="hp2-disclosure">虚构演示项目，不是研究或监控结果。</small>}<div className="hp2-dialog-footer"><Button size="sm" disabled={!allowed||blocked||!callbacks.onDelete} title={actionTitle('delete')} onClick={()=>open({kind:'delete',project:current})}>删除主页条目</Button><Button variant="primary" disabled={!allowed||blocked||!callbacks.onUpdate} title={actionTitle('edit')} onClick={()=>open({kind:'edit',project:current})}>编辑资料</Button></div></div></Modal>}
    {intent&&(intent.kind==='create'||intent.kind==='edit')&&<ProjectForm item={intent.project} mode={context.mode} pending={busy} unsettled={unresolved(operation)} blocked={blocked||operation?.error?.code==='VERSION_CONFLICT'} close={()=>{if(!busy)setIntent(null);}} save={save}><OperationMessage operation={operation} onReconcile={callbacks.onReconcile?reconcile:undefined} busy={busy}/>{operation?.error?.code==='VERSION_CONFLICT'&&<div className="hp2-immutable">关闭窗口并重新读取最新资料后，再决定是否提交。</div>}</ProjectForm>}
    {intent&&!['create','edit'].includes(intent.kind)&&<Modal title={intent.kind==='add'?'加入主页':intent.kind==='delete'?'删除主页条目':'从主页移除'} destructive pending={busy} close={()=>{if(!busy)setIntent(null);}}><div className="hp2-dialog-body"><h2>{intent.project?.record.name}</h2><p>{intent.kind==='add'?'明确加入主页，保留当前进度和项目资料。':'仅移出主页。项目资料、canonical ID、审计和监控引用保留，监控状态保持原样。'}</p><OperationMessage operation={operation} onReconcile={callbacks.onReconcile?reconcile:undefined} busy={busy}/><div className="hp2-dialog-footer"><Button size="sm" data-initial-focus data-dialog-cancel disabled={busy} onClick={()=>setIntent(null)}>取消</Button><Button variant={intent.kind==='add'?'primary':'danger'} disabled={blocked||!allowed} onClick={confirm}>{busy?'提交中…':intent.kind==='add'?'确认加入':'确认移除主页'}</Button></div></div></Modal>}
  </div>;
}

function ProjectForm({item,mode,pending,unsettled,blocked,close,save,children}:{item?:ProjectView;mode:HomepageContext['mode'];pending:boolean;unsettled:boolean;blocked:boolean;close:()=>void;save:(fields:ProjectFieldsProjection)=>Promise<boolean>;children:React.ReactNode}){
  const [initial]=useState(()=>item?pickFields(item.record):emptyFields);
  const [fields,setFields]=useState<ProjectFieldsProjection>(initial),[error,setError]=useState(''),[discard,setDiscard]=useState(false);
  const dirty=JSON.stringify(initial)!==JSON.stringify(fields);
  const exit=()=>{if(pending)return;if(dirty&&!unsettled)setDiscard(true);else close();};
  function update<K extends keyof ProjectFieldsProjection>(key:K,value:ProjectFieldsProjection[K]){setFields(previous=>({...previous,[key]:value}));setError('');}
  async function submit(event:React.FormEvent){event.preventDefault();if(blocked)return;const payload={...pickFields(fields),name:fields.name.trim()};const invalid=validateFields(payload);if(invalid){setError(invalid);return;}await save(payload);}
  return <Modal title={item?'编辑项目资料':'添加项目'} pending={pending} close={discard?()=>setDiscard(false):exit}>{discard?<div className="hp2-dialog-body"><h2>放弃未保存的修改？</h2><div className="hp2-dialog-footer"><Button size="sm" data-initial-focus autoFocus onClick={()=>setDiscard(false)}>继续编辑</Button><Button variant="danger" onClick={close}>放弃修改</Button></div></div>:<form className="hp2-form" onSubmit={submit}>
    <div className="hp2-form-note">{mode==='demo'?'演示编辑 · 操作由模拟回调处理':'操作由接入方回调处理，服务端仍需验证权限与版本。'}</div>
    <div className="hp2-form-grid"><Input label="项目名称" aria-label="项目名称" data-initial-focus required maxLength={120} value={fields.name} disabled={blocked} onChange={event=>update('name',event.target.value)}/><Select label="评分" disabled={blocked} value={fields.rating||''} onChange={event=>update('rating',event.target.value?event.target.value as ProjectFieldsProjection['rating']:null)}><option value="">未评分</option>{ratings.map(rating=><option key={rating}>{rating}</option>)}</Select>
      <Input label="分类" maxLength={80} value={fields.category||''} disabled={blocked} onChange={event=>update('category',event.target.value||null)}/><Input label="官网" type="url" value={fields.website_url||''} disabled={blocked} onChange={event=>update('website_url',event.target.value||null)} placeholder="https://"/>
      <Select label="进度阶段" value={fields.progress_stage} disabled={blocked} onChange={event=>update('progress_stage',event.target.value as ProjectFieldsProjection['progress_stage'])}>{progressStages.map(stage=><option value={stage} key={stage}>{stageLabels[stage]}</option>)}</Select><Input label="进度百分比（未知留空）" type="number" min={0} max={100} step="any" value={fields.progress_percent??''} disabled={blocked} onChange={event=>update('progress_percent',event.target.value===''?null:event.target.valueAsNumber)}/>
      <Input label="发币日期" type="date" value={fields.token_date||''} disabled={blocked} onChange={event=>setFields(previous=>({...previous,token_date:event.target.value||null,token_date_status:event.target.value?(previous.token_date_status==='unconfirmed'?'estimated':previous.token_date_status):'unconfirmed'}))}/><Select label="日期状态" value={fields.token_date_status} disabled={blocked||!fields.token_date} onChange={event=>update('token_date_status',event.target.value as ProjectFieldsProjection['token_date_status'])}>{fields.token_date?<><option value="estimated">预计</option><option value="confirmed">已确认</option></>:<option value="unconfirmed">未确认</option>}</Select></div>
    {item&&<div className="hp2-immutable">发现时间和服务端 ID/时间只读；版本 {item.record.revision}。</div>}
    <label>项目简介<textarea className="ik-input" aria-label="项目简介" rows={3} maxLength={4000} disabled={blocked} value={fields.description} onChange={event=>update('description',event.target.value)}/></label><label>备注 / 下一步<textarea className="ik-input" aria-label="备注 / 下一步" rows={3} maxLength={4000} disabled={blocked} value={fields.notes} onChange={event=>update('notes',event.target.value)}/></label>
    {error&&<div className="hp2-alert error" role="alert">{error}</div>}{children}<div className="hp2-dialog-footer"><Button size="sm" disabled={pending} onClick={exit}>{blocked&&!pending?'关闭':'取消'}</Button><Button type="submit" variant="primary" disabled={blocked}><Icon name="check" width={14} height={14}/>{pending?'提交中…':item?'保存修改':'添加项目'}</Button></div>
  </form>}</Modal>;
}
