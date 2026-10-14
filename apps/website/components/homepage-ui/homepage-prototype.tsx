'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import {ArrowDown,ArrowUp,ArrowUpDown,ArrowUpRight,Check,CheckCheck,ChevronRight,FlaskConical,FolderOpen,FolderSearch,Info,Menu,MoreHorizontal,Plus,RotateCcw,Search,SlidersHorizontal,SquarePen,Trash2,X} from './icons';
import {Modal,Button,Input,Select,Textarea,Badge} from './ui-port';
import {categories,grades,safeWebsite,stages,type HomepageProjectStore,type ProjectRecord,type ProjectSnapshot} from './model/project';

type SortKey='discoveredOn'|'grade'|'name'|'progress';
type Confirmation={kind:'remove'|'delete'|'reset';ids:string[]};
const scoreOrder:Record<string,number>={S:5,A:4,B:3,C:2,'待定':1};
function Grade({value}:{value:ProjectRecord['grade']}){return <Badge className={`hp-grade grade-${value==='待定'?'pending':value}`}>{value}</Badge>;}
function Progress({project}:{project:ProjectRecord}){return <div className="hp-progress"><span className={`hp-stage stage-${stages.indexOf(project.stage)}`}><i/>{project.stage}</span><span className="hp-progress-value">{project.progress}%</span><div className="hp-progress-track"><span style={{width:`${project.progress}%`}}/></div></div>;}
function Website({project,onDemo}:{project:ProjectRecord;onDemo:()=>void}){
  const url=safeWebsite(project.website);
  if(!url)return <span className="hp-muted">—</span>;
  const isExample=new URL(url).hostname.endsWith('.example');
  return <a className="hp-website" href={url} target="_blank" rel="noopener noreferrer" title={isExample?'演示官网占位地址':url} onClick={e=>{e.stopPropagation();if(isExample){e.preventDefault();onDemo();}}}><span>{new URL(url).hostname.replace(/^www\./,'').replace(/\.example$/,'.example')}</span><ArrowUpRight size={13}/></a>;
}

export default function HomepagePrototype({store,readOnly=false}:{store:HomepageProjectStore;readOnly?:boolean}) {
  const [snapshot,setSnapshot]=useState<ProjectSnapshot>({revision:0,items:[]});
  const [ready,setReady]=useState(false),[storageError,setStorageError]=useState('');
  const [tab,setTab]=useState<'active'|'removed'>('active');
  const [query,setQuery]=useState(''),[grade,setGrade]=useState(''),[stage,setStage]=useState(''),[category,setCategory]=useState('');
  const [sort,setSort]=useState<{key:SortKey;direction:'asc'|'desc'}>({key:'grade',direction:'desc'});
  const [selected,setSelected]=useState<string[]>([]);
  const [detail,setDetail]=useState<string|null>(null),[editor,setEditor]=useState<ProjectRecord|null|undefined>(undefined);
  const [menuTop,setMenuTop]=useState(0);
  const [menu,setMenu]=useState<string|null>(null),[confirm,setConfirm]=useState<Confirmation|null>(null),[deleteText,setDeleteText]=useState('');
  const [toast,setToast]=useState<{text:string;undo?:()=>void}|null>(null),[compact,setCompact]=useState(true);
  const searchRef=useRef<HTMLInputElement>(null),selectAllRef=useRef<HTMLInputElement>(null);
  useEffect(()=>{if(readOnly){setSelected([]);setMenu(null);setEditor(undefined);setConfirm(null);setToast(null);}},[readOnly]);
  useEffect(()=>{
    try{setSnapshot(store.load());}catch(e){setStorageError((e as Error).message);}finally{setReady(true);}
    return store.subscribe(next=>{setSnapshot(next);setSelected([]);setToast({text:'已同步另一个标签页的演示修改。'});});
  },[store]);
  useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(null),8000);return ()=>clearTimeout(timer);},[toast]);
  useEffect(()=>{if(!menu)return;const close=(e:MouseEvent)=>{if(!(e.target as Element).closest('[data-row-menu]'))setMenu(null);};const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')setMenu(null);};document.addEventListener('click',close);document.addEventListener('keydown',escape);return ()=>{document.removeEventListener('click',close);document.removeEventListener('keydown',escape);};},[menu]);
  useEffect(()=>{const key=(e:KeyboardEvent)=>{const target=e.target as HTMLElement;if(e.key==='/'&&!['INPUT','SELECT','TEXTAREA'].includes(target.tagName)&&!document.querySelector('dialog[open]')){e.preventDefault();searchRef.current?.focus();}};window.addEventListener('keydown',key);return ()=>window.removeEventListener('keydown',key);},[]);
  const active=snapshot.items.filter(p=>p.membership==='active'),removed=snapshot.items.filter(p=>p.membership==='removed');
  const filtered=useMemo(()=>snapshot.items.filter(p=>p.membership===tab&&(!grade||p.grade===grade)&&(!stage||p.stage===stage)&&(!category||p.category===category)&&(!query.trim()||[p.name,p.description,p.notes,p.category,p.website].join(' ').toLowerCase().includes(query.trim().toLowerCase()))).sort((a,b)=>{
    const value=sort.key==='grade'?scoreOrder[a.grade]-scoreOrder[b.grade]:sort.key==='progress'?a.progress-b.progress:a[sort.key].localeCompare(b[sort.key],'zh-CN',{numeric:true});
    return (sort.direction==='asc'?value:-value)||a.id.localeCompare(b.id);
  }),[snapshot,tab,query,grade,stage,category,sort]);
  const selectedVisible=filtered.filter(p=>selected.includes(p.id));
  const current=snapshot.items.find(p=>p.id===detail);
  useEffect(()=>{if(selectAllRef.current)selectAllRef.current.indeterminate=selectedVisible.length>0&&selectedVisible.length<filtered.length;},[selectedVisible.length,filtered.length]);
  const notice=(text:string)=>setToast({text});
  const demoWebsite=()=>notice('这是演示官网占位地址（.example）。接入后将打开项目的真实官网。');
  function commit(items:ProjectRecord[]):boolean {
    if(readOnly){notice('当前为只读界面演示，不能修改项目。');return false;}
    try{setSnapshot(store.commit(items,snapshot.revision));setStorageError('');return true;}catch(e){notice((e as Error).message);try{setSnapshot(store.load());}catch{/* preserve load error */}return false;}
  }
  function changeSort(key:SortKey){setSort(s=>({key,direction:s.key===key&&s.direction==='desc'?'asc':'desc'}));}
  function clearFilters(){setQuery('');setGrade('');setStage('');setCategory('');setSelected([]);}
  function switchTab(value:typeof tab){setTab(value);setSelected([]);setMenu(null);setDetail(null);}
  function request(kind:Confirmation['kind'],ids:string[]=[]){if(readOnly)return;setConfirm({kind,ids});setDeleteText('');setMenu(null);}
  function restore(ids:string[]){if(commit(snapshot.items.map(p=>ids.includes(p.id)?{...p,membership:'active'}:p))){setSelected([]);notice(`已将 ${ids.length} 个演示项目重新加入主页。`);}}
  function applyConfirmation(){
    if(!confirm||readOnly)return;
    if(confirm.kind==='reset'){
      try{setSnapshot(store.reset(snapshot.revision));setStorageError('');clearFilters();setTab('active');setDetail(null);notice('已恢复初始演示数据。');setConfirm(null);}catch(e){notice((e as Error).message);}return;
    }
    const ids=confirm.ids;
    if(confirm.kind==='delete'){
      if(deleteText!=='删除')return;
      if(commit(snapshot.items.filter(p=>!ids.includes(p.id)))){setDetail(null);setSelected([]);setConfirm(null);notice(`已删除 ${ids.length} 个演示项目。`);}return;
    }
    const previous=snapshot.items.filter(p=>ids.includes(p.id));
    if(commit(snapshot.items.map(p=>ids.includes(p.id)?{...p,membership:'removed'}:p))){
      setDetail(null);setSelected([]);setConfirm(null);
      setToast({text:`已从主页移除 ${ids.length} 个演示项目，资料仍保留。`,undo:()=>{
        try{const latest=store.load();setSnapshot(store.commit(latest.items.map(p=>previous.some(old=>old.id===p.id)?{...p,membership:'active'}:p),latest.revision));notice('已撤销移除。');}catch(e){notice((e as Error).message);}
      }});
    }
  }
  function saveProject(project:ProjectRecord):boolean {
    const exists=snapshot.items.some(p=>p.id===project.id);
    if(!commit(exists?snapshot.items.map(p=>p.id===project.id?project:p):[project,...snapshot.items]))return false;
    notice(exists?'演示项目资料已保存。':'演示项目已添加到主页。');setEditor(undefined);return true;
  }
  const filteredActive=!!(query||grade||stage||category);
  const sortLabel={grade:'评分',discoveredOn:'发现时间',name:'项目名称',progress:'进度'}[sort.key];
  return <div className="hp-root">
    <a className="hp-skip-link" href="#main-content">跳到项目列表</a>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumbs"><span>工作台</span><ChevronRight size={13}/><strong>主页</strong></div><div className="topbar-right"><span className="hp-mode"><FlaskConical size={13}/>UI 原型</span><span className="hp-top-divider"/><span className="hp-top-caption">个人工作空间</span><span className="top-avatar" aria-label="演示工作空间">K</span></div></header>
      <main id="main-content">
        <div className="hp-demo-banner" role="note"><div><FlaskConical size={15}/><strong>演示数据</strong><span>{readOnly?'只读界面演示 · ':''}所有项目、评分与进度均为虚构；修改仅保存在此浏览器。</span></div><Button disabled={readOnly} onClick={()=>request('reset')}><RotateCcw size={12}/>重置演示</Button></div>
        <div className="hp-page-heading"><div><div className="hp-eyebrow">MY WORKSPACE <span>/</span> PROJECTS IN PROGRESS</div><h1>正在做的项目<span className="hp-heading-count">{active.length}</span></h1><p>把研究、参与和下一步行动，放在同一张表里。</p></div><Button className="button primary hp-add" onClick={()=>setEditor(null)} disabled={readOnly||!ready||!!storageError}><Plus size={16}/>添加项目</Button></div>
        <section className="hp-project-panel" aria-label="项目工作列表">
          <div className="hp-panel-top"><div className="hp-tabs" role="tablist" aria-label="项目列表范围"><Button role="tab" aria-selected={tab==='active'} onClick={()=>switchTab('active')}>正在做<span>{active.length}</span></Button><Button role="tab" aria-selected={tab==='removed'} onClick={()=>switchTab('removed')}>已移除<span>{removed.length}</span></Button></div><div className="hp-summary"><span><i className="hp-dot mint"/>{active.filter(p=>p.stage==='进行中').length} 进行中</span><span><i className="hp-dot amber"/>{active.filter(p=>['准备中','研究中'].includes(p.stage)).length} 待推进</span><span><CheckCheck size={12}/>{active.filter(p=>p.stage==='已完成').length} 已完成</span></div></div>
          <div className="hp-toolbar"><div className="hp-search"><Search size={16}/><Input ref={searchRef} aria-label="搜索项目" placeholder="搜索名称、简介、备注…" value={query} onChange={e=>{setQuery(e.target.value);setSelected([]);}}/>{query?<Button className="icon-button" aria-label="清空搜索" onClick={()=>setQuery('')}><X size={13}/></Button>:<kbd>/</kbd>}</div><div className="hp-filters"><SlidersHorizontal size={14}/><Select aria-label="评分筛选" value={grade} onChange={e=>{setGrade(e.target.value);setSelected([]);}}><option value="">全部评分</option>{grades.map(g=><option key={g} value={g}>{g==='待定'?g:`${g} 级`}</option>)}</Select><Select aria-label="进度筛选" value={stage} onChange={e=>{setStage(e.target.value);setSelected([]);}}><option value="">全部进度</option>{stages.map(s=><option key={s}>{s}</option>)}</Select><Select aria-label="分类筛选" value={category} onChange={e=>{setCategory(e.target.value);setSelected([]);}}><option value="">全部分类</option>{Array.from(new Set([...categories,...snapshot.items.map(p=>p.category)])).map(c=><option key={c}>{c}</option>)}</Select></div><div className="hp-sort"><ArrowUpDown size={14}/><Select aria-label="项目排序" value={`${sort.key}:${sort.direction}`} onChange={e=>{const [key,direction]=e.target.value.split(':');setSort({key:key as SortKey,direction:direction as 'asc'|'desc'});}}><option value="grade:desc">评分优先</option><option value="grade:asc">评分由低到高</option><option value="discoveredOn:desc">最新发现</option><option value="discoveredOn:asc">最早发现</option><option value="name:asc">名称 A → Z</option><option value="name:desc">名称 Z → A</option><option value="progress:desc">进度由高到低</option><option value="progress:asc">进度由低到高</option></Select></div><Button className={`hp-density ${compact?'selected':''}`} aria-label={compact?'切换舒适行高':'切换紧凑行高'} aria-pressed={compact} onClick={()=>setCompact(v=>!v)}><Menu size={15}/><span>{compact?'紧凑':'舒适'}</span></Button></div>
          {(filteredActive||selected.length>0)&&<div className="hp-context-bar">{selected.length?<><span><Check size={13}/>已选择 <strong>{selected.length}</strong> 个项目</span>{tab==='active'?<Button onClick={()=>request('remove',selected)}>从主页移除</Button>:<Button onClick={()=>restore(selected)}>重新加入主页</Button>}<Button className="hp-danger-text" onClick={()=>request('delete',selected)}>删除项目</Button><Button className="hp-context-clear" onClick={()=>setSelected([])}>取消选择</Button></>:<><span>筛选结果 <strong>{filtered.length}</strong> 个</span><Button onClick={clearFilters}>清除筛选</Button></>}</div>}
          {tab==='removed'&&<div className="hp-removed-info"><Info size={13}/>从主页移除后，演示项目资料会保留。可重新加入主页，或在确认后删除。</div>}
          {storageError&&<div className="hp-storage-error" role="alert">{storageError}<Button className="button small-button" disabled={readOnly} onClick={()=>request('reset')}>重置演示</Button></div>}
          <div className={`hp-table-scroll ${compact?'compact':''}`} tabIndex={0} aria-label="项目表格，可横向滚动">
            <table className="hp-table"><colgroup><col className="col-check"/><col className="col-project"/><col className="col-grade"/><col className="col-date"/><col className="col-website"/><col className="col-desc"/><col className="col-progress"/><col className="col-notes"/><col className="col-actions"/></colgroup><thead><tr><th><Input type="checkbox" ref={selectAllRef} aria-label="选择当前筛选的全部项目" disabled={readOnly||!filtered.length} checked={filtered.length>0&&selectedVisible.length===filtered.length} onChange={e=>setSelected(e.target.checked?filtered.map(p=>p.id):[])}/></th>{([['name','项目名称'],['grade','评分'],['discoveredOn','发现时间']] as const).map(([key,label])=><th key={key} aria-sort={sort.key===key?(sort.direction==='asc'?'ascending':'descending'):'none'}><Button className="hp-sort-header" onClick={()=>changeSort(key)}>{label}{sort.key===key?(sort.direction==='desc'?<ArrowDown size={12}/>:<ArrowUp size={12}/>):<ArrowUpDown size={11}/>}</Button></th>)}<th>官网</th><th>简介</th><th aria-sort={sort.key==='progress'?(sort.direction==='asc'?'ascending':'descending'):'none'}><Button className="hp-sort-header" onClick={()=>changeSort('progress')}>进度{sort.key==='progress'?(sort.direction==='desc'?<ArrowDown size={12}/>:<ArrowUp size={12}/>):<ArrowUpDown size={11}/>}</Button></th><th>备注 / 下一步</th><th className="hp-actions-th">操作</th></tr></thead><tbody>{filtered.map(p=><tr key={p.id} data-project-id={p.id} className={selected.includes(p.id)?'selected-row':''} onClick={()=>{setDetail(p.id);setMenu(null);}}><td onClick={e=>e.stopPropagation()}><Input type="checkbox" aria-label={`选择 ${p.name}`} disabled={readOnly} checked={selected.includes(p.id)} onChange={e=>setSelected(s=>e.target.checked?[...s,p.id]:s.filter(id=>id!==p.id))}/></td><td><Button className="hp-project-name" onClick={e=>{e.stopPropagation();setDetail(p.id);}}><span className={`hp-project-icon tint-${Number(p.id.replace('demo-',''))%6||0}`}>{p.name.slice(0,1)}</span><span><strong>{p.name}</strong><small>{p.category}<em>演示</em></small></span></Button></td><td><Grade value={p.grade}/></td><td className="hp-date"><time dateTime={p.discoveredOn}>{p.discoveredOn}</time></td><td><Website project={p} onDemo={demoWebsite}/></td><td><span className="hp-cell-copy" title={p.description}>{p.description||'—'}</span></td><td><Progress project={p}/></td><td><span className="hp-cell-copy hp-notes" title={p.notes}>{p.notes||'—'}</span></td><td onClick={e=>e.stopPropagation()}><div className="hp-row-actions"><Button className="icon-button" aria-label={`编辑 ${p.name}`} title={readOnly?'只读界面演示':'编辑资料'} disabled={readOnly} onClick={()=>setEditor(p)}><SquarePen size={15}/></Button><div data-row-menu><Button className="icon-button" aria-label={`更多操作 ${p.name}`} title="更多操作" aria-expanded={menu===p.id} onClick={e=>{setMenuTop(Math.min(e.currentTarget.getBoundingClientRect().bottom+4,window.innerHeight-164));setMenu(menu===p.id?null:p.id);}}><MoreHorizontal size={17}/></Button>{menu===p.id&&<div className="hp-row-menu" style={{top:menuTop}} role="group" aria-label={`${p.name} 操作`}><Button onClick={()=>{setDetail(p.id);setMenu(null);}}><FolderOpen size={14}/>查看资料</Button>{tab==='active'?<Button disabled={readOnly} onClick={()=>request('remove',[p.id])}><X size={14}/>从主页移除</Button>:<Button disabled={readOnly} onClick={()=>{restore([p.id]);setMenu(null);}}><RotateCcw size={14}/>重新加入主页</Button>}<div/><Button className="hp-danger-text" disabled={readOnly} onClick={()=>request('delete',[p.id])}><Trash2 size={14}/>删除项目</Button></div>}</div></div></td></tr>)}</tbody></table>
            {!filtered.length&&<div className="hp-empty"><FolderSearch size={34}/><h3>{!ready?'正在加载演示项目…':storageError?'演示数据暂不可用':filteredActive?'没有匹配的项目':tab==='removed'?'暂无已移除的项目':'主页还没有项目'}</h3><p>{filteredActive?'试试其他关键词，或清除筛选条件。':tab==='removed'?'移除项目后，会在这里保留资料。':'添加一个项目，开始整理你的下一步。'}</p>{filteredActive?<Button className="button small-button" onClick={clearFilters}>清除筛选</Button>:tab==='active'&&!readOnly&&!storageError&&ready?<Button className="button small-button" onClick={()=>setEditor(null)}><Plus size={13}/>添加演示项目</Button>:null}</div>}
          </div>
          <div className="hp-table-footer"><span>显示 <strong>{filtered.length}</strong> / {tab==='active'?active.length:removed.length} 个项目 <i/>排序：{sortLabel}{sort.direction==='desc'?' ↓':' ↑'}</span><span><FlaskConical size={12}/>演示数据 · 本浏览器保存</span></div>
        </section>
        <footer className="hp-page-footer"><span>IKUN.CA <i/>个人项目工作台</span><span>点击项目查看资料 · 编辑、移除与删除均可测试</span></footer>
      </main>
    </div>
    {current&&editor===undefined&&!confirm&&<Modal title="项目资料" close={()=>setDetail(null)}><div className="hp-detail-body"><div className="hp-detail-identity"><span className="hp-detail-avatar">{current.name.slice(0,1)}</span><div><span className="hp-detail-eyebrow">{current.category} <em>演示项目</em></span><h3>{current.name}</h3></div><Grade value={current.grade}/></div><div className="hp-detail-status"><Progress project={current}/><span>{current.membership==='removed'?'已从主页移除':'正在做的项目'}</span></div><dl className="hp-detail-fields"><div><dt>发现时间</dt><dd>{current.discoveredOn}<span className="hp-muted"> · 北京时间</span></dd></div><div><dt>官网</dt><dd><Website project={current} onDemo={demoWebsite}/></dd></div></dl><section><h4>项目简介</h4><p>{current.description||'尚未填写简介。'}</p></section><section><h4>备注 / 下一步</h4><div className="hp-note-block">{current.notes||'尚未添加备注。'}</div></section>{toast&&<div className="hp-detail-notice" role="status">{toast.text}</div>}<div className="hp-detail-disclosure"><FlaskConical size={14}/>该项目的名称、评分、进度与文字均为 UI 演示内容。</div><div className="hp-detail-footer"><Button className="button" disabled={readOnly} onClick={()=>current.membership==='active'?request('remove',[current.id]):restore([current.id])}>{current.membership==='active'?'从主页移除':'重新加入主页'}</Button><Button className="button primary" disabled={readOnly} onClick={()=>setEditor(current)}><SquarePen size={14}/>编辑资料</Button></div></div></Modal>}
    {editor!==undefined&&<ProjectEditor item={editor} items={snapshot.items} close={()=>setEditor(undefined)} save={saveProject}/>}
    {confirm&&<Modal title={confirm.kind==='reset'?'重置演示数据':confirm.kind==='remove'?'从主页移除':'删除项目'} close={()=>setConfirm(null)}><div className="hp-confirm-body"><span className={`hp-confirm-icon ${confirm.kind==='delete'?'danger':''}`}>{confirm.kind==='delete'?<Trash2 size={23}/>:confirm.kind==='reset'?<RotateCcw size={23}/>:<FolderOpen size={23}/>}</span><h3>{confirm.kind==='reset'?'恢复最初的演示列表？':confirm.kind==='remove'?`移除这 ${confirm.ids.length} 个演示项目？`:`删除这 ${confirm.ids.length} 个演示项目？`}</h3><p>{confirm.kind==='reset'?'此浏览器中的演示修改会被清空，恢复 14 个初始演示项目。':confirm.kind==='remove'?'项目将不再显示在“正在做”列表，资料保留在“已移除”中，可随时恢复。':'这会从此浏览器的演示存储中删除项目及资料。删除后不可恢复；仅想隐藏时，请使用“从主页移除”。'}</p>{confirm.kind!=='reset'&&<div className="hp-confirm-names">{snapshot.items.filter(p=>confirm.ids.includes(p.id)).map(p=><span key={p.id}>{p.name}</span>)}</div>}{confirm.kind==='delete'&&<label className="hp-delete-input">输入“删除”以确认<Input data-initial-focus autoFocus value={deleteText} onChange={e=>setDeleteText(e.target.value)} aria-label="删除确认文字" placeholder="删除"/></label>}<div className="hp-modal-footer"><Button className="button" onClick={()=>setConfirm(null)}>取消</Button><Button className={`button ${confirm.kind==='delete'?'hp-danger-button':'primary'}`} disabled={confirm.kind==='delete'&&deleteText!=='删除'} onClick={applyConfirmation}>{confirm.kind==='reset'?'重置演示':confirm.kind==='remove'?'确认移除':'确认删除'}</Button></div></div></Modal>}
    {toast&&!current&&editor===undefined&&!confirm&&<div className="hp-toast" role="status"><Check size={16}/><span>{toast.text}</span>{toast.undo&&<Button onClick={toast.undo}>撤销</Button>}<Button className="icon-button" aria-label="关闭提示" onClick={()=>setToast(null)}><X size={14}/></Button></div>}
  </div>;
}

function ProjectEditor({item,items,close,save}:{item:ProjectRecord|null;items:ProjectRecord[];close:()=>void;save:(project:ProjectRecord)=>boolean}) {
  const initial:ProjectRecord=item||{id:'',name:'',grade:'待定',discoveredOn:new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()),website:'',description:'',category:'基础设施',stage:'研究中',progress:0,notes:'',membership:'active',isDemo:true};
  const [form,setForm]=useState(initial),[error,setError]=useState(''),[discard,setDiscard]=useState(false);
  const dirty=JSON.stringify(form)!==JSON.stringify(initial);
  const exit=()=>dirty?setDiscard(true):close();
  function field<K extends keyof ProjectRecord>(key:K,value:ProjectRecord[K]){setForm(f=>({...f,[key]:value}));setError('');}
  function submit(e:React.FormEvent){
    e.preventDefault();
    const name=form.name.trim(),website=form.website.trim();
    if(!name)return setError('请填写项目名称。');
    if(items.some(p=>p.id!==item?.id&&p.name.trim().toLowerCase()===name.toLowerCase()))return setError('演示列表中已有同名项目，可打开该项目编辑或恢复。');
    if(website&&!safeWebsite(website))return setError('官网请使用有效的 http:// 或 https:// 地址。');
    if(!/^\d{4}-\d{2}-\d{2}$/.test(form.discoveredOn)||Number.isNaN(Date.parse(form.discoveredOn)))return setError('请填写有效的发现日期。');
    if(!save({...form,id:item?.id||crypto.randomUUID(),name,website,isDemo:true}))setError('保存失败，请查看页面提示后重试。');
  }
  return <Modal title={item?'编辑项目资料':'添加项目'} close={discard?()=>setDiscard(false):exit}>{discard?<div className="hp-confirm-body"><h3>放弃未保存的修改？</h3><p>当前修改尚未保存到浏览器演示存储。</p><div className="hp-modal-footer"><Button className="button" onClick={()=>setDiscard(false)}>继续编辑</Button><Button className="button hp-danger-button" onClick={close}>放弃修改</Button></div></div>:<form className="hp-editor-form hp-project-form" onSubmit={submit}><div className="hp-form-notice"><FlaskConical size={13}/>演示编辑 · 仅保存到此浏览器</div><div className="hp-form-grid"><label>项目名称 <span className="hp-required">*</span><Input data-initial-focus autoFocus required maxLength={80} value={form.name} onChange={e=>field('name',e.target.value)} placeholder="输入项目名称"/></label><label>评分<Select aria-label="评分" value={form.grade} onChange={e=>field('grade',e.target.value as ProjectRecord['grade'])}>{grades.map(g=><option key={g}>{g}</option>)}</Select></label><label>发现时间（北京时间）<Input type="date" required value={form.discoveredOn} onChange={e=>field('discoveredOn',e.target.value)}/></label><label>项目分类<Select aria-label="项目分类" value={form.category} onChange={e=>field('category',e.target.value)}>{Array.from(new Set([...categories,form.category])).map(c=><option key={c}>{c}</option>)}</Select></label><label className="hp-field-wide">官网<Input type="url" value={form.website} onChange={e=>field('website',e.target.value)} placeholder="https://project.example" maxLength={500}/></label><label>当前进度<Select aria-label="当前进度" value={form.stage} onChange={e=>field('stage',e.target.value as ProjectRecord['stage'])}>{stages.map(s=><option key={s}>{s}</option>)}</Select></label><label>完成比例（%）<Input type="number" min={0} max={100} step={1} required value={Number.isFinite(form.progress)?form.progress:''} onChange={e=>field('progress',e.target.valueAsNumber)}/></label></div><label>项目简介<Textarea aria-label="项目简介" rows={3} maxLength={1500} value={form.description} onChange={e=>field('description',e.target.value)} placeholder="项目做什么，为什么关注？"/></label><label>备注 / 下一步<Textarea aria-label="备注 / 下一步" rows={3} maxLength={2000} value={form.notes} onChange={e=>field('notes',e.target.value)} placeholder="记录当前进度、待确认事项与下一步行动"/></label>{error&&<div className="hp-form-error" role="alert">{error}</div>}<div className="hp-modal-footer"><Button type="button" className="button" onClick={exit}>取消</Button><Button type="submit" className="button primary"><Check size={14}/>{item?'保存修改':'添加演示项目'}</Button></div></form>}</Modal>;
}
