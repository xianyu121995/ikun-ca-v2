'use client';

import {useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {accountViews,canWrite,displayTime,localDatesToUTC,monitoringLabel,toDiscoveryView,validateProject,type CommandResult,type DiscoveryCallbacks,type DiscoveryDTO,type HunterAccountDTO,type ProjectFields,type PublicError,type ViewContext} from './model';
import s from './discovery.module.css';

export interface HunterDiscoveryProps extends DiscoveryCallbacks {
  context?: ViewContext;
  items: readonly DiscoveryDTO[];
  accounts?: readonly HunterAccountDTO[];
  loading?: boolean;
  refreshing?: boolean;
  error?: PublicError | null;
  nextCursor?: string | null;
  /** Future composition with the single @ikun/ui AppShell; never nest two shells. */
  renderFrame?: (content: ReactNode) => ReactNode;
}
type DialogState = {kind:'discard';next:()=>void}|{kind:'monitor';dto:DiscoveryDTO;project:ProjectFields};
const reviewLabels={pending:'待研究',reviewed:'已整理',tracking:'已确认',ignored:'已忽略'};
const progressLabels={todo:'待开始',researching:'研究中',watching:'观察中',participating:'参与中',completed:'已完成',paused:'已暂停'};
const connectionLabels={unconfigured:'未配置',connecting:'连接中',connected:'已连接',disconnected:'连接中断'};

/** Domain presentation only. No fetch, session, storage, timer, or engine import. */
export function HunterDiscoveryView(props: HunterDiscoveryProps) {
  const {context,items,loading=false,refreshing=false,error}=props;
  const editing=canWrite(context,'can_edit_projects'),managing=canWrite(context,'can_manage_hunter');
  const rows=useMemo(()=>items.slice(0,100).map(toDiscoveryView),[items]);
  const accounts=accountViews(context,props.accounts||[]);
  const [query,setQuery]=useState(''),[rating,setRating]=useState('all'),[review,setReview]=useState('all');
  const [period,setPeriod]=useState('all'),[start,setStart]=useState(''),[end,setEnd]=useState('');
  const [sort,setSort]=useState<'newest'|'oldest'>('newest');
  const [selected,setSelected]=useState<DiscoveryDTO|null>(null),[draft,setDraft]=useState<ProjectFields|null>(null);
  const [feedback,setFeedback]=useState<PublicError|null>(null),[notice,setNotice]=useState('');
  const [dialog,setDialog]=useState<DialogState|null>(null),[busy,setBusy]=useState(false),[showAccounts,setShowAccounts]=useState(false);
  const [commands,setCommands]=useState<Record<string,CommandResult>>({});
  const [uncertainSaves,setUncertainSaves]=useState<Record<string,boolean>>({});
  const lock=useRef(false),dialogRef=useRef<HTMLDialogElement>(null),cancelRef=useRef<HTMLButtonElement>(null);
  const returnFocus=useRef<HTMLElement|null>(null),editorRef=useRef<HTMLInputElement>(null);
  const previousTrigger=useRef<HTMLElement|null>(null);
  const dirty=selected&&draft?JSON.stringify(draft)!==JSON.stringify(selected.project):false;
  const dates=localDatesToUTC(start,end);
  const localFiltersActive=!!query||rating!=='all'||review!=='all'||period!=='all'||sort!=='newest';
  const filtered=rows.filter(r=>{
    if(query&&![r.name,r.handle,r.bio,r.notes,r.source.project.description].join(' ').toLowerCase().includes(query.toLowerCase()))return false;
    if(rating!=='all'&&(rating==='unrated'?r.rating!==null:r.rating!==rating))return false;
    if(review!=='all'&&r.reviewState!==review)return false;
    if(period!=='all'){
      if(r.discoveredEpoch===null)return false;
      if(period==='custom'){if(dates.error||(dates.since&&r.discoveredEpoch<Date.parse(dates.since))||(dates.until&&r.discoveredEpoch>Date.parse(dates.until)))return false;}
      else if(Date.now()-r.discoveredEpoch>Number(period)*3600000)return false;
    }
    return true;
  }).sort((a,b)=>a.discoveredEpoch===null?b.discoveredEpoch===null?0:1:b.discoveredEpoch===null?-1:sort==='newest'?b.discoveredEpoch-a.discoveredEpoch:a.discoveredEpoch-b.discoveredEpoch);
  useEffect(()=>{
    const element=dialogRef.current;
    if(dialog&&!element?.open){returnFocus.current=document.activeElement as HTMLElement;element?.showModal();cancelRef.current?.focus();}
    if(!dialog&&element?.open){element.close();if(returnFocus.current?.isConnected)returnFocus.current.focus();}
  },[dialog]);
  useEffect(()=>{if(selected)editorRef.current?.focus({preventScroll:true});},[selected?.discovery_id]);
  useEffect(()=>{if(!dirty)return;const guard=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue='';};window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard);},[dirty]);
  const changeDraft=(patch:Partial<ProjectFields>)=>setDraft(current=>current?{...current,...patch}:current);
  function guard(next:()=>void){if(lock.current)return;if(dirty)setDialog({kind:'discard',next});else next();}
  function openEditor(dto:DiscoveryDTO,trigger:HTMLElement){guard(()=>{previousTrigger.current=trigger;setSelected(dto);setDraft({...dto.project});setFeedback(null);});}
  function closeEditor(){guard(()=>{setSelected(null);setDraft(null);setFeedback(null);requestAnimationFrame(()=>{if(previousTrigger.current?.isConnected)previousTrigger.current.focus();});});}
  function permissionFailure(){setFeedback({code:'FORBIDDEN',message:'当前账号为只读或缺少所需能力。'});}
  function rememberCommand(id:string,result:CommandResult){setCommands(old=>({...old,[id]:result}));}
  async function save(){
    if(lock.current||!selected||!draft||uncertainSaves[selected.discovery_id])return;
    if(!editing){permissionFailure();return;}
    if(!props.onSaveResearch){setFeedback({code:'NOT_IMPLEMENTED',message:'资料保存回调尚未接入。'});return;}
    const invalid=validateProject(draft);if(invalid){setFeedback({code:'VALIDATION_ERROR',message:invalid});return;}
    lock.current=true;setBusy(true);setFeedback(null);setNotice('');
    try{const result=await props.onSaveResearch({discovery_id:selected.discovery_id,project_id:selected.project_id,expected_revision:selected.revision,project:{...draft}});
      if(!result.ok){setFeedback(result.error);if(['UNKNOWN','UPSTREAM_TIMEOUT'].includes(result.error.code))setUncertainSaves(old=>({...old,[selected.discovery_id]:true}));}
      else if(result.data.discovery_id!==selected.discovery_id||result.data.project_id!==selected.project_id)setFeedback({code:'CONFLICT',message:'保存回调的发现 ID 或项目 ID 与当前记录不一致，未替换资料。'});
      else{setSelected(result.data);setDraft({...result.data.project});setNotice('资料保存回调已确认。');}
    }catch{setUncertainSaves(old=>({...old,[selected.discovery_id]:true}));setFeedback({code:'UNKNOWN',message:'保存结果待核实；草稿已保留，请核对原操作后再处理。'});}
    finally{lock.current=false;setBusy(false);}
  }
  function requestMonitoring(dto:DiscoveryDTO){
    if(lock.current)return;
    if(!managing){permissionFailure();return;}
    if(uncertainSaves[dto.discovery_id]){setFeedback({code:'UNKNOWN',message:'资料保存结果待核实；核对前不能再提交监控写入。'});return;}
    const current=commands[dto.discovery_id];
    if(current&&current.state!=='failed')return;
    if(dto.monitoring_state&&dto.monitoring_state!=='failed')return;
    const project=selected?.discovery_id===dto.discovery_id&&draft?draft:dto.project;
    const invalid=validateProject(project);if(invalid){setFeedback({code:'VALIDATION_ERROR',message:invalid});return;}
    if(!props.onRequestMonitoring){setFeedback({code:'NOT_IMPLEMENTED',message:'人工确认回调尚未接入。'});return;}
    setFeedback(null);setDialog({kind:'monitor',dto,project:{...project}});
  }
  async function confirmMonitoring(){
    if(lock.current||dialog?.kind!=='monitor')return;
    if(!managing){permissionFailure();setDialog(null);return;}
    if(!props.onRequestMonitoring)return;
    const {dto,project}=dialog;lock.current=true;setBusy(true);setFeedback(null);setNotice('');
    try{const result=await props.onRequestMonitoring({discovery_id:dto.discovery_id,expected_revision:dto.revision,confirmed:true,project});
      if(result.ok){rememberCommand(dto.discovery_id,result.data);setNotice(monitoringLabel(result.data.state));setDialog(null);}
      else{setFeedback(result.error);if(['UPSTREAM_TIMEOUT','UNKNOWN'].includes(result.error.code)){rememberCommand(dto.discovery_id,{command_id:'',state:'unknown',project_id:dto.project_id,subscription_id:null,revision:null,updated_at:'',error_code:result.error.code,request_id:result.error.request_id||''});setDialog(null);}}
    }catch{rememberCommand(dto.discovery_id,{command_id:'',state:'unknown',project_id:dto.project_id,subscription_id:null,revision:null,updated_at:'',error_code:'UNKNOWN',request_id:''});setFeedback({code:'UNKNOWN',message:'确认结果待核实；未重复提交。请由适配器核对原操作。'});setDialog(null);}
    finally{lock.current=false;setBusy(false);}
  }
  async function checkCommand(discoveryId:string){
    const cmd=commands[discoveryId];if(lock.current||!cmd?.command_id||!props.onCheckCommand)return;
    lock.current=true;setBusy(true);setFeedback(null);
    try{const result=await props.onCheckCommand(cmd.command_id);if(result.ok&&result.data.command_id===cmd.command_id)rememberCommand(discoveryId,result.data);else setFeedback(result.ok?{code:'CONFLICT',message:'返回的命令 ID 不一致。'}:result.error);}catch{setFeedback({code:'UNKNOWN',message:'命令核对失败；保持待核实状态。'});}finally{lock.current=false;setBusy(false);}
  }
  function monitoringState(dto:DiscoveryDTO){return commands[dto.discovery_id]?.state??dto.monitoring_state;}
  const content=<section className={`${s.root} ${s.referenceLayout} ${selected?s.hasEditor:''}`} aria-label="猎手项目发现" data-mode={context?.mode||'live'}>
    <header className={s.heading}><div><h1>猎手监控 <small>发现值得持续研究的项目</small></h1></div></header>
    <div className={s.referenceStats} aria-label="发现项目概览">
      <div><span>发现项目总数</span><strong>{rows.length}</strong></div>
      <div data-tone="amber"><span><i/>待研究</span><strong>{rows.filter(r=>r.reviewState==='pending').length}</strong></div>
      <div data-tone="green"><span><i/>已整理</span><strong>{rows.filter(r=>r.reviewState==='reviewed').length}</strong></div>
      <div data-tone="blue"><span><i/>已人工确认</span><strong>{rows.filter(r=>r.reviewState==='tracking'||commands[r.key]&&commands[r.key].state!=='failed').length}</strong></div>
      <div data-tone="muted"><span><i/>结果待核实</span><strong>{rows.filter(r=>{const state=commands[r.key]?.state??r.commandState;return state!==null&&state!=='failed';}).length}</strong></div>
      {managing&&<button type="button" className={s.primary} disabled={busy} onClick={()=>{setShowAccounts(!showAccounts);props.onManageHunters?.();}} aria-label="猎手管理">＋ 猎手管理</button>}
    </div>
    <div className={s.boundary}><span className={s.mode}>{context?.mode==='demo'?'演示数据 · 无真实操作':'展示模式 · 适配器注入'}</span>{context?.role==='superadmin'?'人工确认受理后，仍需核对远端监控状态。':'只读模式；无法执行资料修改或监控写入。'}</div>
    {showAccounts&&managing&&<section className={s.accountPanel} aria-label="管理员猎手名单"><h2>猎手账号 · 注入展示</h2><p>这里只显示管理员 DTO；账号编辑由领域窗口提供。此视图不创建、修改或订阅账号。</p><div className={s.scroll}><table><thead><tr><th>账号</th><th>配置意图</th><th>基线</th><th>来源连接</th><th>最近信号</th><th>备注</th></tr></thead><tbody>{accounts.map(a=><tr key={a.account_id}><td>{a.label}<small>@{a.x_handle}</small></td><td>{a.enabled?'已启用':'已停用'}</td><td>{a.baseline_ready?'已建立':'待建立'}</td><td>{connectionLabels[a.connection]||'未知'}</td><td>{displayTime(a.last_signal_at)}</td><td>{a.notes}</td></tr>)}</tbody></table></div>{!accounts.length&&<p>没有授权的猎手账号数据。</p>}</section>}
    <div className={s.filters}><label className={s.search}>搜索<input aria-label="搜索项目" value={query} placeholder="项目、X、简介或备注" onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();setQuery('');}}}/>{query&&<button type="button" onClick={()=>setQuery('')} aria-label="清除搜索">×</button>}</label><label>发现时间<select aria-label="发现时间筛选" value={period} onChange={e=>setPeriod(e.target.value)}><option value="all">全部时间</option><option value="24">近 24H</option><option value="72">近 72H</option><option value="168">近 7 天</option><option value="custom">自定义</option></select></label><label>评分<select aria-label="评分筛选" value={rating} onChange={e=>setRating(e.target.value)}><option value="all">全部评分</option>{['S','A','B','C','D'].map(v=><option key={v}>{v}</option>)}<option value="unrated">未评分</option></select></label><label>状态<select aria-label="状态筛选" value={review} onChange={e=>setReview(e.target.value)}><option value="all">全部状态</option>{Object.entries(reviewLabels).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label><button type="button" disabled={!props.onRefresh||refreshing||busy} title={!props.onRefresh?'数据读取回调未接入':undefined} onClick={props.onRefresh}>{refreshing?'更新中…':'刷新'}</button><button type="button" onClick={()=>{setQuery('');setRating('all');setReview('all');setPeriod('all');setStart('');setEnd('');setSort('newest');}}>重置</button></div>
    {period==='custom'&&<div className={s.dates}><label>开始日期<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>结束日期<input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label><span>北京时间 · 包含首尾日期</span>{dates.error&&<strong role="alert">{dates.error}</strong>}</div>}
    <div className={s.resultbar}><span>{filtered.length} 个项目 <small>· 本页最多 100 条</small></span><span>{refreshing?'更新中，保留现有数据':'北京时间 UTC+8'}</span></div>
    {(feedback||error)&&<div className={s.error} role="alert"><strong>{(feedback||error)?.code}</strong>　{(feedback||error)?.message}{(feedback||error)?.request_id&&<small>请求编号：{(feedback||error)?.request_id}</small>}{(feedback||error)?.code==='VERSION_CONFLICT'&&<p>草稿仍保留。请读取最新资料并核对差异，不会强制覆盖。</p>}<button type="button" disabled={busy||!props.onRefresh} onClick={props.onRefresh}>重新读取</button></div>}
    {notice&&<div className={s.notice} role="status">{notice}<button type="button" onClick={()=>setNotice('')} aria-label="关闭通知">×</button></div>}
    <div className={`${s.grid} ${selected?s.expanded:''}`}>
      <div className={s.tableColumn}><div className={s.scroll} aria-busy={loading||refreshing}>
        {loading&&!rows.length?<div className={s.loading} role="status">正在加载项目…{Array.from({length:8},(_,i)=><div key={i} className={s.skeleton}/>)}</div>:!filtered.length?<div className={s.empty}><h2>{error?'项目列表加载失败':rows.length?'没有符合条件的项目':'还没有项目数据'}</h2><p>{error?'保留公开错误与请求编号，请显式重新读取。':rows.length?'更换关键词或筛选条件。':'等待注入符合 72H 聚合条件的发现 DTO；不会填入示例兜底。'}</p>{rows.length>0&&<button type="button" onClick={()=>{setQuery('');setRating('all');setReview('all');setPeriod('all');}}>清除筛选</button>}</div>:
        <table className={s.discoveryTable}><colgroup><col style={{width:130}}/><col style={{width:205}}/><col/><col style={{width:82}}/><col style={{width:80}}/><col style={{width:158}}/><col style={{width:150}}/></colgroup><thead><tr><th aria-sort={sort==='newest'?'descending':'ascending'}><button type="button" onClick={()=>setSort(sort==='newest'?'oldest':'newest')}>发现时间 {sort==='newest'?'↓':'↑'}</button></th><th>项目 / X 账号</th><th>主页简介</th><th>信号</th><th>评分</th><th>审核 / 确认状态</th><th>操作</th></tr></thead><tbody>{filtered.map(r=>{const command=monitoringState(r.source),blocked=!!uncertainSaves[r.key]||command!==null&&command!=='failed';return <tr key={r.key} data-discovery-id={r.key} data-selected={selected?.discovery_id===r.key||undefined}><td><span className={s.mono}>{r.discoveredLabel}</span><small>{r.canonicalId?'已注册项目':'项目 ID 尚未注册'}</small></td><td><div className={s.referenceProject}><span className={s.referenceProjectAvatar}>{r.name.split(' ').map(w=>w[0]).slice(0,2).join('')}</span><div><strong>{r.name}</strong>{r.xUrl?<a href={r.xUrl} target="_blank" rel="noopener noreferrer">@{r.handle} ↗</a>:<small>账号未知</small>}</div></div></td><td><p title={r.bio}>{r.bio||'主页简介未知'}</p><small>{r.category} · {r.stageLabel}</small></td><td className={s.mono}>{r.signalCount??'未知'}<small>位 · 72H</small></td><td><span className={s.rating} data-grade={r.rating||'none'}>{r.rating||'未评分'}</span></td><td><span className={s.referenceStatus} data-state={r.reviewState||'unknown'}>{r.reviewState?reviewLabels[r.reviewState]:'状态未知'}</span><small data-command-state={command||'none'}>{monitoringLabel(command,r.reviewState||undefined)}</small></td><td><div className={s.rowActions}><button type="button" data-action="open" onClick={e=>openEditor(r.source,e.currentTarget)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg><span>{editing?'编辑':'查看'}</span></button>{managing&&<button type="button" data-action="monitor" disabled={busy||blocked||!props.onRequestMonitoring} title={!props.onRequestMonitoring?'确认回调未接入':blocked?'已有确认结果，需核对原操作':undefined} onClick={()=>requestMonitoring(r.source)}>{blocked?'待核实':'加入监控'}</button>}</div>{commands[r.key]?.command_id&&props.onCheckCommand&&<button type="button" className={s.linkButton} disabled={busy} onClick={()=>checkCommand(r.key)}>核对确认结果</button>}</td></tr>;})}</tbody></table>}
      </div><div className={s.tableFooter}>稳定发现 ID 用于行键；项目 ID 可为空。<button type="button" disabled={localFiltersActive||!props.nextCursor||!props.onNextPage||loading||refreshing} title={localFiltersActive?'请先清除本页筛选；不能复用其他查询的游标':!props.onNextPage?'分页回调未接入':undefined} onClick={()=>{if(props.nextCursor)props.onNextPage?.(props.nextCursor);}}>下一页</button></div></div>
      {selected&&draft&&<aside className={s.editor} aria-label="项目资料面板" onKeyDown={e=>{if(e.key==='Escape'&&!dialog){e.preventDefault();closeEditor();}}}><div className={s.editorHeader}><h2>{editing?'编辑项目资料':'项目资料 · 只读'}{dirty&&<span title="未保存修改"> *</span>}</h2><button type="button" disabled={busy} aria-label="关闭资料面板" onClick={closeEditor}>×</button></div><div className={s.editorIdentity}><span className={s.referenceDetailAvatar}>{selected.project.name.split(' ').map(w=>w[0]).slice(0,2).join('')}</span><div><strong>{selected.project.name}</strong>{toDiscoveryView(selected).xUrl?<a href={toDiscoveryView(selected).xUrl!} target="_blank" rel="noopener noreferrer">@{selected.x_handle} ↗</a>:<span>账号未知</span>}<small>粉丝 {toDiscoveryView(selected).followersLabel}</small></div></div><form id="hunter-research-form" className={s.editorForm} onSubmit={e=>{e.preventDefault();void save();}}><label>项目名称<input ref={editorRef} required maxLength={120} readOnly={!editing||busy} value={draft.name} onChange={e=>changeDraft({name:e.target.value})}/></label><label>官网地址<input type="url" maxLength={1000} readOnly={!editing||busy} value={draft.website_url||''} placeholder="未知时留空" onChange={e=>changeDraft({website_url:e.target.value||null})}/></label><label>赛道<input maxLength={80} readOnly={!editing||busy} value={draft.category||''} placeholder="未知时留空" onChange={e=>changeDraft({category:e.target.value||null})}/></label><div className={s.twoColumns}><label>项目进度<select disabled={!editing||busy} value={Object.hasOwn(progressLabels,draft.progress_stage)?draft.progress_stage:''} onChange={e=>changeDraft({progress_stage:e.target.value as ProjectFields['progress_stage']})}><option value="" disabled>进度未知</option>{Object.entries(progressLabels).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label><label>进度百分比<input type="number" min={0} max={100} step="any" readOnly={!editing||busy} value={draft.progress_percent??''} placeholder="未知" onChange={e=>changeDraft({progress_percent:e.target.value===''?null:Number(e.target.value)})}/></label></div><label>人工简介<textarea readOnly={!editing||busy} rows={3} maxLength={4000} value={draft.description} onChange={e=>changeDraft({description:e.target.value})}/></label><fieldset disabled={!editing||busy}><legend>人工评分</legend><div className={s.ratings}>{(['S','A','B','C','D',null] as const).map(g=><button key={g||'none'} type="button" data-grade={g||'none'} aria-pressed={draft.rating===g} onClick={()=>changeDraft({rating:g})}>{g||'未评分'}</button>)}</div></fieldset><div className={s.twoColumns}><label>发币日期<input type="date" readOnly={!editing||busy} value={draft.token_date||''} onChange={e=>changeDraft({token_date:e.target.value||null,token_date_status:e.target.value?'estimated':'unconfirmed'})}/></label><label>日期状态<select disabled={!editing||busy||!draft.token_date} value={draft.token_date_status} onChange={e=>changeDraft({token_date_status:e.target.value as ProjectFields['token_date_status']})}><option value="unconfirmed">未确认</option><option value="estimated">预计</option><option value="confirmed">已确认</option></select></label></div><label>研究备注<textarea readOnly={!editing||busy} rows={3} maxLength={4000} value={draft.notes} onChange={e=>changeDraft({notes:e.target.value})}/></label><div className={s.originalBio}><small>原始主页简介 · 仅文本</small><p>{selected.profile_bio||'未知'}</p></div></form><div className={s.editorFooter}>{editing&&<button type="submit" form="hunter-research-form" className={s.primary} title={!props.onSaveResearch?'资料保存回调未接入':undefined} disabled={busy||!props.onSaveResearch||uncertainSaves[selected.discovery_id]}>{busy?'处理中…':uncertainSaves[selected.discovery_id]?'保存结果待核实':'保存资料'}</button>}{managing&&<button type="button" disabled={busy||uncertainSaves[selected.discovery_id]||!props.onRequestMonitoring||!!monitoringState(selected)&&monitoringState(selected)!=='failed'} onClick={()=>requestMonitoring(selected)}>人工确认监控</button>}{!editing&&<span>只读展示，不提供业务写入</span>}</div></aside>}
    </div>
    <dialog ref={dialogRef} className={s.dialog} tabIndex={-1} onKeyDown={e=>{if(e.key!=='Tab')return;const el=dialogRef.current;if(!el)return;const focusable=Array.from(el.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));const first=focusable[0],last=focusable.at(-1);if(!first){e.preventDefault();el.focus();}else if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}} aria-labelledby="hunter-dialog-title" onCancel={e=>{e.preventDefault();if(!lock.current)setDialog(null);}}><h2 id="hunter-dialog-title">{dialog?.kind==='discard'?'放弃未保存修改？':'人工确认加入监控'}</h2><p>{dialog?.kind==='discard'?'草稿尚未保存，继续会丢弃当前修改。':`${dialog?.kind==='monitor'?dialog.project.name:''} 将提交人工确认请求。受理成功后仍需核对命令结果，不能据此判断远端监控运行。`}</p>{dialog?.kind==='monitor'&&dirty&&<p>将提交当前资料；是否持久保存由注入回调契约决定。</p>}{feedback&&dialog?.kind==='monitor'&&<div className={s.error} role="alert">{feedback.code}：{feedback.message}</div>}<div className={s.dialogFooter}><button ref={cancelRef} type="button" disabled={busy} onClick={()=>setDialog(null)}>取消</button><button type="button" className={s.primary} disabled={busy||dialog?.kind==='monitor'&&!managing} onClick={()=>{if(dialog?.kind==='discard'){const next=dialog.next;setDialog(null);next();}else void confirmMonitoring();}}>{busy?'提交中…':dialog?.kind==='discard'?'放弃修改':'确认提交'}</button></div></dialog>
  </section>;
  return props.renderFrame?props.renderFrame(content):content;
}
