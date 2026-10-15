"use client";

import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import { Button, cx, type Tone } from "./primitives.js";
import { Icon } from "./icons.js";

export function Alert({ tone = "info", title, children, requestId, code, action }: { tone?: Tone; title: string; children?: ReactNode; requestId?: string; code?: string; action?: ReactNode }) {
  return <div className={cx("ik-alert", `ik-tone--${tone}`)} role={tone === "danger" ? "alert" : "status"}>
    <Icon name={tone === "success" ? "check" : "warning"} /><div><strong>{title}</strong>{children && <div className="ik-alert-detail">{children}</div>}{code && <small className="ik-mono">错误代码：{code}</small>}{requestId && <small className="ik-mono">请求编号：{requestId}</small>}</div>{action && <div className="ik-alert-action">{action}</div>}
  </div>;
}
export function EmptyState({ title = "暂无数据", description, action }: { title?: string; description?: string; action?: ReactNode }) {
  return <div className="ik-empty"><span className="ik-empty-icon"><Icon name="layers" /></span><h3>{title}</h3>{description && <p>{description}</p>}{action}</div>;
}
export function ErrorState({ title = "数据加载失败", description = "请稍后重试。已加载的数据会保留。", requestId, code, onRetry, pending = false }: { title?: string; description?: string; requestId?: string; code?: string; onRetry?: () => void; pending?: boolean }) {
  return <Alert tone="danger" title={title} {...(requestId ? { requestId } : {})} {...(code ? { code } : {})} {...(onRetry ? { action: <Button pending={pending} size="sm" onClick={onRetry} icon={<Icon name="refresh" />}>重试</Button> } : {})}>{description}</Alert>;
}
export function Skeleton({ label = "正在加载", lines = 3 }: { label?: string; lines?: number }) {
  return <div className="ik-skeleton-block" aria-busy="true"><span className="ik-sr-only" role="status">{label}</span>{Array.from({ length: Math.max(1, Math.min(12, lines)) }, (_, i) => <span className="ik-skeleton" aria-hidden="true" key={i} />)}</div>;
}

export interface DialogProps { open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; children: ReactNode; footer?: ReactNode; pending?: boolean; closeOnBackdrop?: boolean; initialFocusRef?: RefObject<HTMLElement | null>; destructive?: boolean }
export function Dialog({ open, onOpenChange, title, description, children, footer, pending = false, closeOnBackdrop = false, initialFocusRef, destructive = false }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null); const titleId = useId(); const descriptionId = useId();
  // Native modal dialogs make the outside document inert; Tab wrapping below also
  // prevents WebViews from moving focus to their browser chrome at the boundary.
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) { dialog.showModal(); (initialFocusRef?.current ?? (destructive ? dialog.querySelector<HTMLElement>("[data-dialog-cancel]") : null))?.focus(); }
    if (!open && dialog.open) dialog.close();
  }, [open, initialFocusRef, destructive]);
  useEffect(() => { if (open && pending) ref.current?.focus(); }, [open, pending]);
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [open]);
  useEffect(() => { const dialog = ref.current; return () => { if (dialog?.open) dialog.close(); }; }, []);
  return <dialog ref={ref} tabIndex={-1} className="ik-theme ik-dialog" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined} aria-modal="true" aria-busy={pending} onSubmitCapture={e => {
    const submitter = (e.nativeEvent as SubmitEvent).submitter;
    const method = (submitter instanceof HTMLButtonElement || submitter instanceof HTMLInputElement) && submitter.hasAttribute("formmethod") ? submitter.formMethod : e.target instanceof HTMLFormElement ? e.target.method : undefined;
    if (pending || method === "dialog") e.preventDefault();
    if (pending) e.stopPropagation();
  }} onCancel={e => { e.preventDefault(); if (!pending) onOpenChange(false); }} onKeyDown={e => {
    if (e.key !== "Tab") return;
    const dialog = e.currentTarget;
    const candidates = Array.from(dialog.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href], [tabindex]')).filter(element => element.tabIndex >= 0 && !element.matches(":disabled") && element.getClientRects().length > 0 && !element.closest("[inert]"));
    const first = candidates[0]; const last = candidates.at(-1);
    if (!first || !last) { e.preventDefault(); dialog.focus(); return; }
    if (e.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (document.activeElement === last || document.activeElement === dialog)) { e.preventDefault(); first.focus(); }
  }} onClick={e => {
    if (!closeOnBackdrop || pending || e.target !== e.currentTarget) return;
    const bounds = e.currentTarget.getBoundingClientRect();
    if (e.clientX < bounds.left || e.clientX > bounds.right || e.clientY < bounds.top || e.clientY > bounds.bottom) onOpenChange(false);
  }}>
    <div className="ik-dialog-head"><div><h2 id={titleId}>{title}</h2>{description && <p id={descriptionId}>{description}</p>}</div><Button variant="ghost" size="sm" disabled={pending} aria-label="关闭弹窗" onClick={() => onOpenChange(false)}><Icon name="close" /></Button></div>
    <div className="ik-dialog-body">{children}</div>{footer && <div className="ik-dialog-footer">{footer}</div>}
  </dialog>;
}

export interface ToastMessage { id: string; title: string; description?: string; tone?: Tone }
function ToastItem({ message, onDismiss }: { message: ToastMessage; onDismiss: (id: string) => void }) {
  const dismissRef = useRef(onDismiss); dismissRef.current = onDismiss;
  useEffect(() => {
    if (message.tone === "danger" || message.tone === "warning") return;
    const timeout = window.setTimeout(() => dismissRef.current(message.id), 5000);
    return () => window.clearTimeout(timeout);
  }, [message.id, message.tone]);
  return <div className={cx("ik-toast", `ik-tone--${message.tone ?? "info"}`)} role={message.tone === "danger" ? "alert" : "status"}><div><strong>{message.title}</strong>{message.description && <p>{message.description}</p>}</div><Button variant="ghost" size="sm" aria-label={`关闭通知：${message.title}`} onClick={() => onDismiss(message.id)}><Icon name="close" /></Button></div>;
}
export function ToastViewport({ messages, onDismiss }: { messages: readonly ToastMessage[]; onDismiss: (id: string) => void }) {
  return <div className="ik-theme ik-toasts" aria-label="操作通知">{messages.map(message => <ToastItem key={message.id} message={message} onDismiss={onDismiss} />)}</div>;
}
