'use client';
import {useEffect,useState} from 'react';
export default function HealthBanner(){
 const [errors,setErrors]=useState<string[]>([]);
 useEffect(()=>{let stopped=false;const check=async()=>{try{const r=await fetch('/api/v1/system/health',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(r.status===401||r.status===403)return;if(!r.ok)throw Error();const v=await r.json();if(!stopped)setErrors(v.data.errors);}catch{if(!stopped)setErrors(['健康检查暂不可用']);}};void check();const timer=setInterval(()=>void check(),60000);return()=>{stopped=true;clearInterval(timer);};},[]);
 return errors.length?<div role='alert' style={{background:'#7f1d1d',color:'#fff',padding:'10px 20px',position:'sticky',top:0,zIndex:1000}}>服务异常：{errors.join('；')}</div>:null;
}
