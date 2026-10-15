'use client';

import {useEffect,useState,type ReactNode} from 'react';
import s from './discovery.module.css';

/** Screenshot-specific preview chrome. Not a second public AppShell or a live account UI. */
export function ReferencePreviewFrame({children,tools,role}:{children:ReactNode;tools:ReactNode;role:'superadmin'|'user'|'unconnected'}) {
  const [controls,setControls]=useState(false),[notice,setNotice]=useState(''),[clock,setClock]=useState('');
  useEffect(()=>{const update=()=>setClock(new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date()));update();const timer=setInterval(update,1000);return()=>clearInterval(timer);},[]);
  const roleLabel=role==='superadmin'?'超级管理员':role==='user'?'普通用户 · 只读':'未接入账号';
  return <div className={s.referenceFrame}>
    <aside className={s.referenceSidebar} aria-label="原型导航">
      <button className={s.referenceBrand} type="button" onClick={()=>setNotice('当前原型展示猎手监控。其他业务页面由各自窗口提供。')} aria-label="ikun.ca 原型"><span className={s.referenceBrandMark}><i/><i/><i/><i/></span><span><strong>ikun.ca</strong><small>Crypto Research for<br/>What’s Next</small></span></button>
      <nav className={s.referenceNav} aria-label="三个业务入口">
        <button type="button" aria-label="首页" onClick={()=>setNotice('首页由独立页面窗口提供，当前仍是猎手监控交互原型。')}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 10 9-7 9 7v11h-6v-7H9v7H3z"/></svg><span>首页</span></button>
        <button type="button" className={s.referenceActive} aria-current="page" aria-label="猎手监控" onClick={()=>setNotice('当前页面：猎手监控。可以搜索、编辑资料、评分和人工确认监控。')}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="8" r="4"/><circle cx="16" cy="16" r="4"/><path d="m11 5 5-2 5 5-2 5M5 11l-2 5 5 5 5-2"/></svg><span>猎手监控</span></button>
        <button type="button" aria-label="猎手项目监控" onClick={()=>setNotice('猎手项目监控由独立窗口接入；本页负责发现项目及研究资料。')}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="7" cy="7" r="3"/><circle cx="17" cy="7" r="3"/><circle cx="7" cy="17" r="3"/><circle cx="17" cy="17" r="3"/><path d="m9 9 6 6M15 9l-6 6"/></svg><span>猎手项目监控</span></button>
      </nav>
      <div className={s.referenceAccount}><button type="button" onClick={()=>setNotice(`${roleLabel}，仅为演示身份。真实账号及权限由认证模块接入。`)}><span className={s.referenceUserAvatar}>{role==='user'?'U':'A'}</span><span><strong>{role==='unconnected'?'未接入':role==='user'?'Demo User':'Admin'}</strong><small>{roleLabel}</small></span><span>⌄</span></button><button type="button" disabled title="账号设置尚未接入">⚙ <span>设置 · 未接入</span></button><button type="button" disabled title="这是本地原型，没有真实登录会话">↪ <span>退出登录 · 未接入</span></button></div>
    </aside>
    <div className={s.referenceMain}><header className={s.referenceTopbar}><div className={s.referenceBreadcrumb}>工作台 <span>›</span><strong>猎手监控</strong></div><div className={s.referenceTopActions}><span className={s.referenceEnvironment}><i/>本地原型</span><button type="button" aria-expanded={controls} aria-controls="hunter-preview-settings" onClick={()=>setControls(!controls)}>交互设置</button><button type="button" className={s.referenceNotification} aria-label="查看原型通知" onClick={()=>setNotice('暂无真实通知。页面全部使用演示数据，不会发送平台请求。')}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9a6 6 0 0 1 12 0v7l2 2H4l2-2zM10 21h4M10 2h4"/></svg></button><button type="button" className={s.referenceTopAvatar} aria-label="查看演示账号" onClick={()=>setNotice(`${roleLabel} · 演示账号，没有真实登录会话。`)}>{role==='user'?'U':'A'}</button></div></header>
      <div className={s.referenceOutlet}><div className={s.referenceClock}>{clock}<span>UTC+8</span></div>{children}</div>
    </div>
    <section hidden={!controls} id="hunter-preview-settings" className={s.referenceSettings} aria-label="原型交互设置"><header><strong>交互演示设置</strong><button type="button" aria-label="关闭交互设置" onClick={()=>setControls(false)}>×</button></header>{tools}<p>仅改变本地演示的身份、回调结果与页面状态。</p></section>
    {notice&&<div className={s.referenceToast} role="status"><span>{notice}</span><button type="button" aria-label="关闭原型提示" onClick={()=>setNotice('')}>×</button></div>}
  </div>;
}
