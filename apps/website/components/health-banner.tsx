'use client';
import {useEffect,useState} from 'react';
// Owner 2026-10-19: the banner refreshes every 30s and disappears by itself once the problem is gone; short blips are
// filtered server-side (3 min). It can be closed with ✕; the same set of problems then stays hidden, new ones show again.
const KEY='ikun.health.dismissed';
type Usage={day:string;used:number;limit:number;backfill_used:number;backfill_limit:number;recording_since:number;by_program:{program:string;calls:number}[]};
export default function HealthBanner(){
 const [usage,setUsage]=useState<Usage|null>(null);
 const [csrf,setCsrf]=useState<string|null>(null),[checking,setChecking]=useState(false),[checkMessage,setCheckMessage]=useState('');
 useEffect(()=>{let stopped=false;void fetch('/api/auth/session',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(v=>{if(!stopped&&v?.data?.user?.role==='superadmin'&&typeof v.data.csrf_token==='string')setCsrf(v.data.csrf_token);}).catch(()=>{});return()=>{stopped=true;};},[]);
 const check=async()=>{if(!csrf||checking)return;setChecking(true);try{const r=await fetch('/api/v1/system/provider-check',{method:'POST',headers:{'x-csrf-token':csrf,'content-type':'application/json'},body:'{}',signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error();const v=await r.json();setCheckMessage(v.data.blocked_by_quota?'检查已排队；额度恢复前不会反复请求':'已提交一次检查');}catch{setCheckMessage('检查未提交，请稍后手动重试');}finally{setChecking(false);}};
 const [errors,setErrors]=useState<string[]>([]),[dismissed,setDismissed]=useState<string|null>(null);
 useEffect(()=>{try{setDismissed(window.sessionStorage.getItem(KEY));}catch{/* optional */}},[]);
 useEffect(()=>{let stopped=false,failures=0;const check=async()=>{try{const r=await fetch('/api/v1/system/health',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(r.status===401||r.status===403)return;if(!r.ok)throw Error();const v=await r.json();failures=0;if(!stopped){setErrors(v.data.errors);setUsage(v.data.provider_6551??null);}}catch{failures+=1;if(!stopped&&failures>=3)setErrors(['健康检查暂不可用']);}};void check();const timer=setInterval(()=>void check(),30000);return()=>{stopped=true;clearInterval(timer);};},[]);
 const signature=errors.join('；');
 const show=errors.length>0&&dismissed!==signature;
 const close=()=>{setDismissed(signature);try{window.sessionStorage.setItem(KEY,signature);}catch{/* optional */}};
 return <>{show&&<div role='alert' style={{background:'#7f1d1d',color:'#fff',padding:'10px 48px 10px 20px',position:'sticky',top:0,zIndex:1000}}>服务异常：{signature}<button type='button' aria-label='关闭提示' title='关闭（同样的问题不再提示，出现新问题会再显示）' onClick={close} style={{position:'absolute',right:12,top:'50%',transform:'translateY(-50%)',background:'transparent',border:0,color:'#fff',fontSize:18,cursor:'pointer',lineHeight:1}}>✕</button></div>}
 {usage&&<details style={{padding:'6px 20px',fontSize:12,background:'#172132',color:'#dbeafe'}}><summary>6551 今日调用 {usage.used} / {usage.limit} 次（北京时间）</summary>
 <div>{usage.by_program.length?usage.by_program.map(r=><span key={r.program} style={{marginRight:18}}>{({tracking:'追踪',hunter:'猎手',hunter_ai:'猎手资料补全'} as Record<string,string>)[r.program]??r.program}：{r.calls}次</span>):'今日尚无调用'}</div>
 <div>补抓 {usage.backfill_used} / {usage.backfill_limit} 次；开始记录：{new Date(usage.recording_since*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}。此前历史用量不计入本表。</div>
 {csrf&&<button type='button' onClick={()=>void check()} disabled={checking}>{checking?'提交中…':'检查'}</button>} {checkMessage}</details>}</>;
}
