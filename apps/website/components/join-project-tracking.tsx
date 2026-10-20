'use client';
import {useRef,useState} from 'react';
import {Button,Input} from '@ikun/ui';
import {normalizeXHandle,type ProjectTrackingResult} from '../lib/project-tracking-model';

export function JoinProjectTracking({projectId,csrf,canManage,disabled=false,onJoined}:{projectId:string;csrf:string;canManage:boolean;disabled?:boolean;onJoined?:()=>void}) {
  const [busy,setBusy]=useState(false),[input,setInput]=useState(false),[handle,setHandle]=useState(''),[message,setMessage]=useState(''),[failed,setFailed]=useState(false);
  const flight=useRef(false),key=useRef<{handle:string;key:string}|null>(null);
  if(!canManage)return null;
  const url='/api/v1/tracking/project-entry?project_id='+encodeURIComponent(projectId);
  async function api(method='GET',body?:unknown,revision?:number,requestKey?:string):Promise<ProjectTrackingResult> {
    const response=await fetch(url,{method,credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(15_000),headers:{'content-type':'application/json','x-csrf-token':csrf,...(requestKey?{'idempotency-key':requestKey}:{}),...(revision?{'if-match':`"rev-${revision}"`}:{})},...(body?{body:JSON.stringify(body)}:{})});
    const result=await response.json();if(!response.ok)throw Error(result.error?.message||'加入追踪失败');return result.data;
  }
  async function join(manual=false) {
    if(flight.current||disabled)return;
    const supplied=manual?normalizeXHandle(handle):null;
    if(manual&&!supplied){setFailed(true);setMessage('X 用户名只能包含 1–15 位字母、数字和下划线');return;}
    flight.current=true;setBusy(true);setFailed(false);setMessage('');
    try {
      const ready=await api();
      if(ready.status==='already'){setInput(false);setMessage(ready.message);return;}
      const username=ready.x_handle??supplied;
      if(!username){setInput(true);setMessage(ready.warning||'请填写这个项目的 X 用户名');return;}
      // Retain the original key across uncertain network retries. A fresh server read still checks duplicates first.
      if(key.current?.handle!==username)key.current={handle:username,key:crypto.randomUUID()};
      const result=await api('POST',{x_handle:username},ready.project_revision,key.current!.key);
      setMessage(result.message);setInput(false);key.current=null;if(result.status==='added')onJoined?.();
    }catch(error){setFailed(true);setMessage(error instanceof Error&&error.name!=='TimeoutError'&&error.name!=='AbortError'?error.message:'结果暂未确认，请再次点击核对；不会恢复或删除已有订阅');}
    finally{flight.current=false;setBusy(false);}
  }
  return <div className="join-project-tracking">
    <Button pending={busy} disabled={disabled||busy} onClick={()=>void join()}>{busy?'加入中…':'加入追踪'}</Button>
    {input&&<div role="group" aria-label="填写 X 账号" style={{display:'flex',gap:8,flexWrap:'wrap',alignItems:'end',marginTop:8}}>
      <Input autoFocus label="X 用户名" placeholder="@handle" value={handle} disabled={busy||disabled} onChange={event=>setHandle(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();void join(true);}}}/>
      <Button disabled={busy||disabled} onClick={()=>void join(true)}>确认加入</Button><Button disabled={busy} onClick={()=>{setInput(false);setMessage('');}}>取消填写</Button>
    </div>}
    {message&&<p role={failed?'alert':'status'} style={{color:failed?'#fca5a5':'inherit',margin:'8px 0'}}>{message}</p>}
  </div>;
}
