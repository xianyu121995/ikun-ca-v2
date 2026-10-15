'use client';
import {useRef,useState,type AnchorHTMLAttributes} from 'react';
import {AppShell,Select} from '@ikun/ui';
import '@ikun/ui/styles.css';
import ReferenceHomepage from './reference-homepage';
import {DEMO_AS_OF,referenceFixtures} from '../../features/homepage/reference-fixtures';
import {pickFields} from '../../features/homepage/view-model';
import type {HomepageData,HomepageQuery,OperationResult,ProjectRecordProjection,ProjectRef} from '../../features/homepage/types';
import type {ArchiveNote,EditorDraft,ProjectMilestone,ReferenceCallbacks} from '../../features/homepage/reference-types';

function PreviewLink(props:AnchorHTMLAttributes<HTMLAnchorElement>&{href:string}){return <a {...props} title="本次仅验收主页，其他页面由对应窗口开发" onClick={event=>event.preventDefault()}/>;}
export default function Phase2Preview(){
  const [initial]=useState(referenceFixtures),[items,setItems]=useState(initial.projects),[milestones,setMilestones]=useState(initial.milestones),[archiveNotes,setArchiveNotes]=useState<ArchiveNote[]>([]);
  const [mode,setMode]=useState<'demo'|'live'>('demo'),[role,setRole]=useState<'superadmin'|'user'>('superadmin'),[scenario,setScenario]=useState('success'),[listCase,setListCase]=useState('ready');
  const [calls,setCalls]=useState(0),[last,setLast]=useState('尚未调用回调'),[query,setQuery]=useState<HomepageQuery|null>(null),[foundDate,setFoundDate]=useState<string|null>(null);
  const counter=useRef(0),generation=useRef(0),pendingApply=useRef<null|(()=>void)>(null);
  function audit(name:string,payload:unknown){counter.current++;setCalls(counter.current);setLast(JSON.stringify({name,payload}));}
  function result(chosen:string):OperationResult{
    const request_id=`demo-reference-request-${counter.current}`;
    if(chosen==='denied'||chosen==='conflict')return {state:'failed',request_id,error:{code:chosen==='denied'?'FORBIDDEN':'VERSION_CONFLICT',message:chosen==='denied'?'模拟权限拒绝。':'模拟版本冲突，请重新读取项目资料。',retryable:false,request_id}};
    if(chosen==='timeout')return {state:'unknown',request_id,error:{code:'UPSTREAM_TIMEOUT',message:'模拟写入超时，结果待核实。',retryable:false,request_id}};
    return {state:chosen==='success'?'succeeded':chosen as OperationResult['state'],request_id,command_id:null};
  }
  async function perform(name:string,payload:unknown,apply:()=>void):Promise<OperationResult>{
    audit(name,payload);const issued=generation.current;
    await new Promise(resolve=>setTimeout(resolve,450));
    if(scenario==='throw')throw Error('PRIVATE_DEMO_RAW_ERROR_DO_NOT_DISPLAY');
    const outcome=result(scenario);
    if(issued!==generation.current)return {...outcome,state:'unknown'};
    if(outcome.state==='succeeded'){apply();pendingApply.current=null;}
    else if(['accepted','pending','running','unknown'].includes(outcome.state))pendingApply.current=apply;
    return outcome;
  }
  function patch(ref:ProjectRef,transform:(project:ProjectRecordProjection)=>ProjectRecordProjection){setItems(previous=>previous.map(project=>project.project_id===ref.project_id?{...transform(project),revision:project.revision+1}:project));}
  function remember(project:ProjectRecordProjection){setArchiveNotes(previous=>[...previous.filter(note=>note.project_id!==project.project_id),{project_id:project.project_id,previous_stage:project.progress_stage,completed_on:DEMO_AS_OF}]);}
  function saveEvent(id:string,draft:EditorDraft){const event:ProjectMilestone={project_id:id,...draft.milestone};setMilestones(previous=>[...previous.filter(item=>item.project_id!==id),event]);}
  const callbacks:ReferenceCallbacks={
    onCreateDraft:draft=>perform('create-draft',draft,()=>{
      const id=`demo-reference-created-${counter.current}`;
      if(draft.archive_after_save)setArchiveNotes(previous=>[...previous,{project_id:id,previous_stage:'researching',completed_on:DEMO_AS_OF}]);
      setItems(previous=>[{...pickFields(draft.fields),project_id:id,home_membership:draft.archive_after_save?'removed':'active',discovered_at:null,revision:1,created_at:'2026-10-15T00:00:00Z',updated_at:'2026-10-15T00:00:00Z'},...previous]);saveEvent(id,draft);
    }),
    onUpdateDraft:(ref,draft)=>perform('update-draft',{target:ref,draft},()=>{
      const current=items.find(project=>project.project_id===ref.project_id);if(current&&draft.archive_after_save)remember(current);
      patch(ref,project=>({...project,...pickFields(draft.fields),home_membership:draft.archive_after_save?'removed':project.home_membership}));saveEvent(ref.project_id,draft);
    }),
    onArchive:targets=>perform('archive',{targets},()=>{for(const target of targets){const current=items.find(project=>project.project_id===target.project_id);if(current)remember(current);}const ids=new Set(targets.map(target=>target.project_id));setItems(previous=>previous.map(project=>ids.has(project.project_id)?{...project,progress_stage:'completed',home_membership:'removed',revision:project.revision+1}:project));}),
    onRestore:target=>perform('restore',{target},()=>{const previous=archiveNotes.find(note=>note.project_id===target.project_id);patch(target,project=>({...project,home_membership:'active',progress_stage:previous?.previous_stage||project.progress_stage}));setArchiveNotes(notes=>notes.filter(note=>note.project_id!==target.project_id));}),
    onMembership:(target,action)=>perform('membership',{target,action},()=>patch(target,project=>({...project,home_membership:action==='add'?'active':'removed'}))),
    onDelete:target=>perform('delete',{target},()=>patch(target,project=>({...project,home_membership:'removed'}))),
    onReconcile:async original=>{audit('reconcile',{request_id:original.request_id});await new Promise(resolve=>setTimeout(resolve,250));const outcome=result(scenario);if(outcome.state==='succeeded'){pendingApply.current?.();pendingApply.current=null;}return outcome;},
    onQueryChange:next=>setQuery(next),
    onDiscoveryDateChange:setFoundDate,
    onReload:()=>{setListCase('refreshing');setTimeout(()=>setListCase('ready'),400);},
    onNextPage:cursor=>audit('next-cursor',{cursor}),
  };
  const error={code:'UPSTREAM_UNAVAILABLE',message:'模拟数据读取失败，保留已加载内容。',retryable:true,request_id:'demo-reference-list'};
  const data:HomepageData=mode==='live'?{status:'error',items:[],next_cursor:null,error:{code:'AUTH_NOT_CONFIGURED',message:'Live 数据提供者尚未接入，没有演示回退。',retryable:false,request_id:null}}:{status:listCase==='loading'?'loading':listCase==='empty'?'empty':listCase.includes('error')?'error':'ready',items:['loading','empty','error'].includes(listCase)?[]:items,next_cursor:listCase==='page'?'demo-next-cursor':null,refreshing:listCase==='refreshing',error:listCase.includes('error')?error:null};
  return <div className="hpv2-preview"><AppShell pathname="/" LinkComponent={PreviewLink} account={mode==='demo'?{name:'演示账号',detail:`模拟 ${role}`,href:'/auth'}:undefined} footer="主页 UI 原型 · 演示数据">
    <details className="hpv2-demo-settings"><summary>演示设置 · 无真实请求</summary><div className="hpv2-demo-controls"><strong>验收控制台 · 所有结果均为模拟</strong>
      <Select label="数据模式" value={mode} onChange={event=>{generation.current++;pendingApply.current=null;setMode(event.target.value as typeof mode);}}><option value="demo">demo</option><option value="live">live（未接入）</option></Select>
      <Select label="模拟权限" disabled={mode==='live'} value={role} onChange={event=>setRole(event.target.value as typeof role)}><option value="superadmin">superadmin</option><option value="user">user · 只读</option></Select>
      <Select label="列表状态演示" disabled={mode==='live'} value={listCase} onChange={event=>setListCase(event.target.value)}>{['ready','loading','empty','error','refreshing','refresh-error','page'].map(value=><option key={value}>{value}</option>)}</Select>
      <Select label="回调结果演示" disabled={mode==='live'} value={scenario} onChange={event=>setScenario(event.target.value)}>{['success','denied','timeout','conflict','accepted','pending','running','unknown','throw'].map(value=><option key={value}>{value}</option>)}</Select>
      <output aria-label="操作回调次数">回调 {calls} 次</output><details><summary>查看回调参数</summary><pre data-testid="callback-log">{last}</pre><pre data-testid="query-log">{JSON.stringify({query,foundDate})}</pre></details>
    </div></details>
    <ReferenceHomepage context={mode==='demo'?{mode,role,capabilities:{can_edit_projects:role==='superadmin'}}:{mode:'live'}} data={data} callbacks={mode==='demo'?callbacks:{}} milestones={mode==='demo'?milestones:[]} archiveNotes={mode==='demo'?archiveNotes:[]} asOfDate={mode==='demo'?DEMO_AS_OF:undefined}/>
  </AppShell></div>;
}
