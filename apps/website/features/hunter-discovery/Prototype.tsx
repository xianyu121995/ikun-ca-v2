'use client';

import {useState} from 'react';
import {HunterDiscoveryView} from './DiscoveryView';
import {ReferencePreviewFrame} from './ReferencePreviewFrame';
import {demoAccounts,demoDiscoveries} from './fixtures';
import type {ActionResult,CommandResult,DiscoveryDTO,MonitoringInput,ProjectFields,PublicError,ViewContext} from './model';
import s from './discovery.module.css';

type Outcome='success'|'forbidden'|'timeout'|'conflict'|'pending'|'unknown';
const failure=(code:string,message:string): ActionResult<never>=>({ok:false,error:{code,message,request_id:'ui0-demo-request'}});
const pause=()=>new Promise<void>(resolve=>setTimeout(resolve,850)); // Demo harness only.
export function HunterPrototype() {
  const [items,setItems]=useState(demoDiscoveries),[role,setRole]=useState<'superadmin'|'user'|'unconnected'>('superadmin');
  const [outcome,setOutcome]=useState<Outcome>('success'),[screen,setScreen]=useState('normal'),[refreshing,setRefreshing]=useState(false);
  const [calls,setCalls]=useState({save:0,monitor:0,check:0,manage:0,next:0});
  const live=role==='unconnected';
  const context:ViewContext|undefined=live?undefined:{mode:'demo',role,capabilities:{can_edit_projects:role==='superadmin',can_manage_hunter:role==='superadmin'}};
  function fakeFailure():ActionResult<never>|null {
    if(outcome==='forbidden')return failure('FORBIDDEN','演示：注入回调拒绝权限，未保存任何数据。');
    if(outcome==='timeout')return failure('UPSTREAM_TIMEOUT','演示：回调超时，结果待核实，请先核对原操作。');
    if(outcome==='conflict')return failure('VERSION_CONFLICT','演示：服务端版本已变化，草稿已保留。');
    return null;
  }
  const error:PublicError|null=screen==='error'?{code:'UPSTREAM_UNAVAILABLE',message:'演示：列表请求失败；没有回退到虚构的实时数据。',request_id:'ui0-demo-list'}:null;
  async function onSaveResearch(input:{discovery_id:string;project_id:string|null;expected_revision:number;project:ProjectFields}):Promise<ActionResult<DiscoveryDTO>> {
    setCalls(c=>({...c,save:c.save+1}));await pause();if(outcome==='pending')return new Promise(()=>{});
    const failed=fakeFailure();if(failed)return failed;
    if(outcome==='unknown')throw new Error('private implementation error must never be displayed');
    const dto=items.find(p=>p.discovery_id===input.discovery_id)!;
    const updated:DiscoveryDTO={...dto,project:{...input.project},revision:dto.revision+1,review_state:'reviewed'};
    setItems(old=>old.map(p=>p.discovery_id===dto.discovery_id?updated:p));return {ok:true,data:updated};
  }
  async function onRequestMonitoring(input:MonitoringInput):Promise<ActionResult<CommandResult>> {
    setCalls(c=>({...c,monitor:c.monitor+1}));await pause();if(outcome==='pending')return new Promise(()=>{});
    const failed=fakeFailure();if(failed)return failed;
    const dto=items.find(p=>p.discovery_id===input.discovery_id)!;
    return {ok:true,data:{command_id:`cmd_00000000-0000-4000-8000-${String(items.indexOf(dto)+1).padStart(12,'0')}`,state:outcome==='unknown'?'unknown':'accepted',project_id:dto.project_id,subscription_id:null,revision:null,updated_at:'2026-10-14T22:00:00Z',error_code:null,request_id:'ui0-demo-confirm'}};
  }
  function refresh(){setRefreshing(true);setTimeout(()=>{setRefreshing(false);setScreen('normal');},850);}
  const tools=<div className={s.demoTools} aria-label="隔离演示控制台"><strong>UI0 · 合成数据与回调演示</strong><label>展示身份<select aria-label="演示身份" value={role} onChange={e=>setRole(e.target.value as typeof role)}><option value="superadmin">superadmin</option><option value="user">user · 只读</option><option value="unconnected">无会话 / 未接入</option></select></label><label>回调结果<select aria-label="演示回调结果" value={outcome} onChange={e=>setOutcome(e.target.value as Outcome)}><option value="success">成功受理</option><option value="forbidden">403 拒绝权限</option><option value="timeout">超时 · 待核实</option><option value="conflict">409 版本冲突</option><option value="pending">持续 pending</option><option value="unknown">unknown</option></select></label><label>页面状态<select aria-label="演示页面状态" value={screen} onChange={e=>setScreen(e.target.value)}><option value="normal">正常数据</option><option value="loading">首次加载</option><option value="empty">空数据</option><option value="error">加载失败</option></select></label><output data-testid="callback-count">save:{calls.save} monitor:{calls.monitor} check:{calls.check} manage:{calls.manage} next:{calls.next}</output><span>没有真实会话、API、数据库或后台任务。刷新清空内存演示。</span></div>;
  return <HunterDiscoveryView renderFrame={content=><ReferencePreviewFrame tools={tools} role={role}>{content}</ReferencePreviewFrame>} key={role} context={context} items={live||screen==='loading'||screen==='empty'||screen==='error'?[]:items} accounts={live?[]:demoAccounts} loading={screen==='loading'} refreshing={refreshing} error={error} nextCursor={live?null:'opaque-demo-cursor'} onSaveResearch={live?undefined:onSaveResearch} onRequestMonitoring={live?undefined:onRequestMonitoring} onCheckCommand={live?undefined:async(commandId)=>{setCalls(c=>({...c,check:c.check+1}));await pause();return {ok:true,data:{command_id:commandId,state:'accepted',project_id:null,subscription_id:null,revision:null,updated_at:'2026-10-14T22:00:00Z',error_code:null,request_id:'ui0-demo-check'}};}} onRefresh={live?undefined:refresh} onManageHunters={live?undefined:()=>setCalls(c=>({...c,manage:c.manage+1}))} onNextPage={live?undefined:()=>setCalls(c=>({...c,next:c.next+1}))}/>;
}
