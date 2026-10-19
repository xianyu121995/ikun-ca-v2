'use client';
import {useEffect,useState} from 'react';
// Owner 2026-10-19: the banner refreshes every 30s and disappears by itself once the problem is gone; short blips are
// filtered server-side (3 min). It can be closed with ✕; the same set of problems then stays hidden, new ones show again.
const KEY='ikun.health.dismissed';
export default function HealthBanner(){
 const [errors,setErrors]=useState<string[]>([]),[dismissed,setDismissed]=useState<string|null>(null);
 useEffect(()=>{try{setDismissed(window.sessionStorage.getItem(KEY));}catch{/* optional */}},[]);
 useEffect(()=>{let stopped=false,failures=0;const check=async()=>{try{const r=await fetch('/api/v1/system/health',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(r.status===401||r.status===403)return;if(!r.ok)throw Error();const v=await r.json();failures=0;if(!stopped)setErrors(v.data.errors);}catch{failures+=1;if(!stopped&&failures>=3)setErrors(['健康检查暂不可用']);}};void check();const timer=setInterval(()=>void check(),30000);return()=>{stopped=true;clearInterval(timer);};},[]);
 const signature=errors.join('；');
 if(!errors.length||dismissed===signature)return null;
 const close=()=>{setDismissed(signature);try{window.sessionStorage.setItem(KEY,signature);}catch{/* optional */}};
 return <div role='alert' style={{background:'#7f1d1d',color:'#fff',padding:'10px 48px 10px 20px',position:'sticky',top:0,zIndex:1000}}>服务异常：{signature}<button type='button' aria-label='关闭提示' title='关闭（同样的问题不再提示，出现新问题会再显示）' onClick={close} style={{position:'absolute',right:12,top:'50%',transform:'translateY(-50%)',background:'transparent',border:0,color:'#fff',fontSize:18,cursor:'pointer',lineHeight:1}}>✕</button></div>;
}
