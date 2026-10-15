"use client";

import { useId, useState, type FormEventHandler, type ReactNode } from "react";
import { Alert } from "./feedback.js";
import { Badge, Button, Input, Panel, type Tone } from "./primitives.js";
import { Icon } from "./icons.js";

export interface LoginPanelProps {
  onSubmit: FormEventHandler<HTMLFormElement>; pending?: boolean; error?: string; notice?: ReactNode;
  footer?: ReactNode; disabled?: boolean;
}
export function LoginPanel({ onSubmit, pending = false, error, notice, footer, disabled = false }: LoginPanelProps) {
  const [visible, setVisible] = useState(false); const passwordId = useId();
  return <div className="ik-theme ik-auth-layout"><div className="ik-login">
    <a href="/" className="ik-brand ik-auth-brand"><span className="ik-brand-mark" aria-hidden="true">ik</span><span className="ik-brand-text">ikun<span>.ca</span><small>WEB3 TERMINAL</small></span></a>
    <Panel><p className="ik-eyebrow">安全访问</p><h1>登录工作空间</h1><p className="ik-login-intro">查看项目，跟进信号，管理你的工作空间。</p>
      {notice && <div className="ik-login-notice">{notice}</div>}
      <form className="ik-form" method="post" action="/api/v1/auth/login" onSubmit={e => { e.preventDefault(); if (!pending && !disabled) onSubmit(e); }} aria-busy={pending}>
        <Input label="账号" name="username" required autoComplete="username" autoCapitalize="none" spellCheck={false} disabled={pending || disabled} placeholder="输入账号" />
        <div className="ik-password-field"><Input id={passwordId} label="密码" name="password" type={visible ? "text" : "password"} required autoComplete="current-password" disabled={pending || disabled} /><button type="button" className="ik-password-toggle" aria-label={visible ? "隐藏密码" : "显示密码"} aria-pressed={visible} aria-controls={passwordId} disabled={pending || disabled} onClick={() => setVisible(!visible)}><Icon name="eye" /></button></div>
        {error && <Alert tone="danger" title="登录未完成">{error}</Alert>}
        <Button type="submit" variant="primary" pending={pending} disabled={disabled} icon={<Icon name="arrow" />}>{pending ? "登录中…" : "登录"}</Button>
      </form>{footer && <div className="ik-login-footer">{footer}</div>}
    </Panel><p className="ik-auth-note">会话与访问权限由工作空间认证服务管理。</p>
  </div></div>;
}

export interface AccountSummaryProps { name: string; identifier: string; roleLabel: string; statusLabel: string; statusTone?: Tone; children?: ReactNode; actions?: ReactNode }
export function AccountSummary({ name, identifier, roleLabel, statusLabel, statusTone = "neutral", children, actions }: AccountSummaryProps) {
  return <Panel title="账号信息" {...(actions ? { actions } : {})}><div className="ik-account-summary"><span className="ik-avatar ik-avatar--large" aria-hidden="true">{Array.from(name)[0]?.toUpperCase() ?? "?"}</span><div><h3>{name}</h3><p className="ik-mono">{identifier}</p></div><div className="ik-account-badges"><Badge>{roleLabel}</Badge><Badge tone={statusTone}>{statusLabel}</Badge></div></div>{children && <div className="ik-account-details">{children}</div>}</Panel>;
}
