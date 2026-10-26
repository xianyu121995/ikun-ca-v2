'use client';
import { Children, cloneElement, isValidElement, useState, useEffect, type FormEvent, type ReactNode } from 'react';
import { Alert, Button, Input, LoginPanel, Panel, type NavigationLinkProps } from '@ikun/ui';
import Link from 'next/link';
import {clearClientSession} from '../../lib/client-session-cache';

/** Receiving-only wording approved by the owner; preserve the frozen shared UI. */
// Owner decision 2026-10-18: workspace pages switch without a full reload so the site-wide voice keeps playing.
const WORKSPACE=new Set(['/','/hunter','/tracking','/intel']);
function A(p:NavigationLinkProps){return WORKSPACE.has(p.href)?<Link {...p} href={p.href} prefetch={true}/>:<a {...p}/>;}
export function WorkspaceLink({children,href,...props}:NavigationLinkProps) {
  if(href!=='/tracking')return <A {...props} href={href}>{children}</A>;
  return <A {...props} href={href} aria-label="猎手项目追踪" title="猎手项目追踪">{Children.map(children,child=>
    isValidElement<{children?:ReactNode}>(child)&&child.type==='span'
      ?cloneElement(child,undefined,'猎手项目追踪'):child)}</A>;
}

async function call(path:string,data:object,csrf?:string) {
  const response=await fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',
    headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':csrf}:{})},body:JSON.stringify(data),signal:AbortSignal.timeout(10000)});
  const value=await response.json();
  if(!response.ok) throw new Error(value.error?.message??'操作未完成，请重试');
  return value.data;
}
async function csrfToken() {
  const response=await fetch('/api/v1/auth/me',{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!response.ok) {location.replace('/login');throw new Error('会话已失效，请重新登录');}
  return (await response.json()).data.csrf_token as string;
}
function safeNext() {
  const path=new URLSearchParams(location.search).get('next')??'/';
  return /^\/(?:$|hunter(?:\/|$)|tracking(?:\/|$))/.test(path)&&!/[\\\r\n]/.test(path)?path:'/';
}
export function LoginForm() {
  const [pending,setPending]=useState(false),[error,setError]=useState('');
  async function submit(event:FormEvent<HTMLFormElement>) {
    const form=event.currentTarget,values=new FormData(form);setPending(true);setError('');
    try {const session=await call('/api/v1/auth/login',{username:values.get('username'),password:values.get('password')});
      clearClientSession();form.reset();location.replace(session.must_change_password?'/auth/password':safeNext());
    }catch(error){setError(error instanceof Error?error.message:'登录未完成');}finally{setPending(false);}
  }
  const [notice,setNotice]=useState('');
  useEffect(()=>{if(new URLSearchParams(location.search).has('next'))setNotice('请登录，原会话可能已过期。');},[]);
  return <LoginPanel notice={notice} onSubmit={submit} pending={pending} error={error} footer="不开放公开注册。忘记密码请联系本机管理员。" />;
}
export function PasswordForm({forced}:{forced:boolean}) {
  const [pending,setPending]=useState(false),[error,setError]=useState('');
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();const form=event.currentTarget,values=new FormData(form);setError('');
    if(values.get('new_password')!==values.get('confirm_password')) {setError('两次新密码不一致');return;}
    setPending(true);
    try {await call('/api/v1/auth/password',{current_password:values.get('current_password'),new_password:values.get('new_password')},await csrfToken());
      clearClientSession();form.reset();location.replace('/?notice=password_changed');
    }catch(error){setError(error instanceof Error?error.message:'改密未完成');}finally{setPending(false);}
  }
  return <Panel title={forced?'首次登录：修改初始密码':'修改本人密码'}>
    <p>{forced?'必须修改初始密码后才能访问业务。':'修改后会撤销全部旧会话，并安全更新当前会话。'}使用至少 10 个字符的独立长口令。</p>
    <form className="ik-form" method="post" action="/api/v1/auth/password" onSubmit={submit} aria-busy={pending}>
      <Input label="当前密码" name="current_password" type="password" autoComplete="current-password" required maxLength={128} disabled={pending} />
      <Input label="新密码" name="new_password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} disabled={pending} />
      <Input label="确认新密码" name="confirm_password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} disabled={pending} />
      {error&&<Alert title="修改未完成" tone="danger">{error}</Alert>}
      <Button type="submit" variant="primary" pending={pending}>保存新密码</Button>
    </form>
  </Panel>;
}
export function LogoutButton() {
  const [pending,setPending]=useState(false),[error,setError]=useState('');
  return <><Button pending={pending} onClick={async()=>{setPending(true);setError('');try{
    await call('/api/v1/auth/logout',{},await csrfToken());clearClientSession();location.replace('/login');
  }catch(error){setError(error instanceof Error?error.message:'退出未完成');}finally{setPending(false);}}}>退出登录</Button>
  {error&&<span role="alert">{error}</span>}</>;
}
