'use client';
import {useRef,useState} from 'react';
import Phase2Homepage from './phase2-homepage';
import {AppShell,Select} from '@ikun/ui';
import '@ikun/ui/styles.css';
import {phase2Fixtures} from '../../features/homepage/demo-fixtures';
import type {HomepageCallbacks,HomepageData,HomepageQuery,OperationResult,ProjectFieldsProjection,ProjectRecordProjection,ProjectRef} from '../../features/homepage/types';

export default function Phase2Preview(){
  const [items,setItems]=useState(phase2Fixtures),[mode,setMode]=useState<'demo'|'live'>('demo'),[role,setRole]=useState<'user'|'superadmin'>('superadmin');
  const [scenario,setScenario]=useState('success'),[listCase,setListCase]=useState('ready');
  const [calls,setCalls]=useState(0),[last,setLast]=useState('尚未调用回调'),[query,setQuery]=useState<HomepageQuery|null>(null);
  const counter=useRef(0),pendingApply=useRef<null|(()=>void)>(null);
  function audit(name:string,payload:unknown){counter.current++;setCalls(counter.current);setLast(JSON.stringify({name,payload}));}
  function result(chosen:string):OperationResult{
    const request_id=`demo-request-${counter.current}`;
    if(chosen==='denied'||chosen==='conflict')return {state:'failed',request_id,error:{code:chosen==='denied'?'FORBIDDEN':'VERSION_CONFLICT',message:chosen==='denied'?'模拟权限拒绝。':'模拟版本冲突，请重新读取项目资料。',retryable:false,request_id}};
    if(chosen==='timeout')return {state:'unknown',request_id,error:{code:'UPSTREAM_TIMEOUT',message:'模拟写入超时，结果待核实。',retryable:false,request_id}};
    return {state:chosen==='success'?'succeeded':chosen as OperationResult['state'],request_id,command_id:null};
  }
  async function perform(name:string,payload:unknown,apply:()=>void):Promise<OperationResult>{
    audit(name,payload);
    await new Promise(resolve=>setTimeout(resolve,500)); // Demo-only delay for pending UI tests.
    if(scenario==='throw')throw new Error('PRIVATE_DEMO_RAW_ERROR_DO_NOT_DISPLAY');
    const outcome=result(scenario);
    if(outcome.state==='succeeded'){apply();pendingApply.current=null;}else if(['accepted','pending','running','unknown'].includes(outcome.state))pendingApply.current=apply;
    return outcome;
  }
  function patch(ref:ProjectRef,transform:(project:ProjectRecordProjection)=>ProjectRecordProjection){
    setItems(previous=>previous.map(project=>project.project_id===ref.project_id?{...transform(project),revision:project.revision+1}:project));
  }
  const callbacks:HomepageCallbacks={
    onCreate:(fields:ProjectFieldsProjection)=>perform('create',fields,()=>setItems(previous=>[{...fields,project_id:`demo-created-${counter.current}`,home_membership:'active',discovered_at:null,revision:1,created_at:'2026-10-15T00:00:00.000Z',updated_at:'2026-10-15T00:00:00.000Z'},...previous])),
    onUpdate:(ref,fields)=>perform('update',{target:ref,fields},()=>patch(ref,project=>({...project,...fields}))),
    onMembership:(ref,action)=>perform('membership',{target:ref,action},()=>patch(ref,project=>({...project,home_membership:action==='add'?'active':'removed'}))),
    onDelete:ref=>perform('delete',{target:ref},()=>patch(ref,project=>({...project,home_membership:'removed'}))),
    onReconcile:async previous=>{audit('reconcile',{request_id:previous.request_id});await new Promise(resolve=>setTimeout(resolve,250));const outcome=result(scenario);if(outcome.state==='succeeded'){pendingApply.current?.();pendingApply.current=null;}return outcome;},
    onQueryChange:next=>setQuery(next),
    onReload:()=>{setListCase('refreshing');setTimeout(()=>setListCase('ready'),400);},
    onNextPage:cursor=>{audit('next-page',{cursor});},
  };
  const error={code:'UPSTREAM_UNAVAILABLE',message:'模拟数据读取失败，保留已加载内容。',retryable:true,request_id:'demo-list-request'};
  const data:HomepageData=mode==='live'?{status:'error',items:[],next_cursor:null,error:{code:'AUTH_NOT_CONFIGURED',message:'Live 数据提供者尚未接入，没有演示回退。',retryable:false,request_id:null}}:
    {status:listCase==='loading'?'loading':listCase==='empty'?'empty':listCase.includes('error')?'error':'ready',
      items:['loading','empty','error'].includes(listCase)?[]:items,next_cursor:listCase==='page'?'demo-next-cursor':null,
      refreshing:listCase==='refreshing',error:listCase.includes('error')?error:null};
  return <div className="hp2-preview"><AppShell pathname="/" account={mode==='demo'?{name:'演示账号',detail:`模拟 ${role}`,href:'/auth'}:undefined} footer="主页 UI 原型 · 演示数据">
    <div className="hp2-demo-controls"><strong>UI0 演示控制台 · 无真实请求</strong>
      <Select label="数据模式" value={mode} onChange={event=>{setMode(event.target.value as typeof mode);pendingApply.current=null;}}><option value="demo">demo</option><option value="live">live（未接入）</option></Select>
      <Select label="模拟权限" disabled={mode==='live'} value={role} onChange={event=>setRole(event.target.value as typeof role)}><option value="superadmin">superadmin</option><option value="user">user · 只读</option></Select>
      <Select label="列表状态演示" disabled={mode==='live'} value={listCase} onChange={event=>setListCase(event.target.value)}>{['ready','loading','empty','error','refreshing','refresh-error','page'].map(value=><option key={value}>{value}</option>)}</Select>
      <Select label="回调结果演示" disabled={mode==='live'} value={scenario} onChange={event=>setScenario(event.target.value)}>{['success','denied','timeout','conflict','accepted','pending','running','unknown','throw'].map(value=><option key={value}>{value}</option>)}</Select>
      <output aria-label="操作回调次数">回调 {calls} 次</output><details><summary>查看回调参数</summary><pre data-testid="callback-log">{last}</pre><pre data-testid="query-log">{JSON.stringify(query)}</pre></details>
    </div>
    <Phase2Homepage context={mode==='demo'?{mode,role,capabilities:{can_edit_projects:role==='superadmin'}}:{mode:'live'}} data={data} callbacks={mode==='demo'?callbacks:{}}/>
  </AppShell></div>;
}
