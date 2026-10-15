"use client";

import { useId, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type RefAttributes, type SelectHTMLAttributes } from "react";
import { Icon } from "./icons.js";

export function cx(...values: (string | false | null | undefined)[]): string { return values.filter(Boolean).join(" "); }
export type Tone = "neutral" | "success" | "info" | "warning" | "danger";
export type UiOperationState = "idle" | "pending" | "running" | "succeeded" | "failed" | "unknown";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, RefAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  pending?: boolean;
  icon?: ReactNode;
  readOnly?: boolean;
  disabledReason?: string;
  operationState?: UiOperationState;
  mode?: "demo" | "live";
  canExecute?: boolean;
}
export function Button({ variant = "secondary", size = "md", pending = false, icon, disabled, children, className, type = "button", readOnly = false, disabledReason, operationState, mode, canExecute, "aria-describedby": describedBy, ...props }: ButtonProps) {
  const reasonId = useId(); const unknown = operationState === "unknown";
  const busy = !unknown && (pending || operationState === "pending" || operationState === "running");
  const capabilityDenied = mode === "live" && canExecute !== true;
  const blocked = Boolean(disabled || busy || readOnly || unknown || capabilityDenied);
  const reason = blocked && !busy ? (unknown ? `结果待核实，请先核对回执${disabledReason ? `；${disabledReason}` : ""}` : disabledReason || (readOnly ? "当前账号只读" : capabilityDenied ? "当前操作权限未确认" : undefined)) : undefined;
  const button = <button {...props} type={type} disabled={blocked} aria-busy={busy || undefined} aria-describedby={[describedBy, reason ? reasonId : ""].filter(Boolean).join(" ") || undefined} className={cx("ik-button", `ik-button--${variant}`, `ik-button--${size}`, className)}>
    {busy ? <span className="ik-spinner" aria-hidden="true" /> : icon}{children}
  </button>;
  return reason ? <span className="ik-button-with-reason">{button}<span className="ik-hint" id={reasonId}>{reason}</span></span> : button;
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement>, RefAttributes<HTMLInputElement> { label: string; hint?: string; error?: string }
export function Input({ label, hint, error, id, className, "aria-describedby": describedBy, ...props }: InputProps) {
  const generated = useId(); const fieldId = id ?? generated;
  const description = [describedBy, hint ? `${fieldId}-hint` : "", error ? `${fieldId}-error` : ""].filter(Boolean).join(" ") || undefined;
  return <div className={cx("ik-field", className)}>
    <label className="ik-label" htmlFor={fieldId}>{label}{props.required && <span aria-hidden="true"> *</span>}</label>
    <input {...props} id={fieldId} className="ik-input" aria-invalid={error ? true : props["aria-invalid"]} aria-describedby={description} />
    {hint && <p className="ik-hint" id={`${fieldId}-hint`}>{hint}</p>}
    {error && <p className="ik-field-error" id={`${fieldId}-error`}>{error}</p>}
  </div>;
}

export interface SearchInputProps { label: string; value: string; onValueChange: (value: string) => void; placeholder?: string; disabled?: boolean }
export function SearchInput({ label, value, onValueChange, placeholder = "搜索名称、关键词…", disabled = false }: SearchInputProps) {
  const id = useId();
  return <div className="ik-search">
    <label className="ik-sr-only" htmlFor={id}>{label}</label><Icon name="search" />
    <input id={id} type="search" value={value} disabled={disabled} placeholder={placeholder} onChange={e => onValueChange(e.target.value)} onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); onValueChange(""); } }} />
    {value && <button type="button" disabled={disabled} aria-label={`清除${label}`} onClick={() => { onValueChange(""); document.getElementById(id)?.focus(); }}><Icon name="close" /></button>}
  </div>;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement>, RefAttributes<HTMLSelectElement> { label: string; hint?: string; error?: string }
export function Select({ label, id, hint, error, className, children, "aria-describedby": describedBy, ...props }: SelectProps) {
  const generated = useId(); const fieldId = id ?? generated;
  return <div className={cx("ik-field", className)}>
    <label className="ik-label" htmlFor={fieldId}>{label}</label>
    <select {...props} id={fieldId} className="ik-input" aria-invalid={error ? true : props["aria-invalid"]} aria-describedby={[describedBy, hint ? `${fieldId}-hint` : "", error ? `${fieldId}-error` : ""].filter(Boolean).join(" ") || undefined}>{children}</select>
    {hint && <p id={`${fieldId}-hint`} className="ik-hint">{hint}</p>}{error && <p id={`${fieldId}-error`} className="ik-field-error">{error}</p>}
  </div>;
}

export function Badge({ tone = "neutral", children, className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return <span {...props} className={cx("ik-badge", `ik-tone--${tone}`, className)}>{children}</span>;
}
export type ScoreGrade = "S" | "A" | "B" | "C" | "D";
export function ScoreBadge({ grade, value }: { grade?: ScoreGrade | null; value?: number | null }) {
  const validGrade = grade && ["S", "A", "B", "C", "D"].includes(grade);
  const validValue = typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
  if (!validGrade) return <span className="ik-score ik-score--unknown">未评分</span>;
  return <span className={cx("ik-score", `ik-score--${grade.toLowerCase()}`)} aria-label={`${grade} 级${validValue ? `，${value} 分` : ""}`}><strong>{grade}</strong>{validValue && <span>{value}</span>}</span>;
}

export function Panel({ title, description, actions, children, className, ...props }: Omit<HTMLAttributes<HTMLElement>, "title"> & { title?: ReactNode; description?: string; actions?: ReactNode }) {
  return <section {...props} className={cx("ik-panel", className)}>{(title || actions) && <div className="ik-panel-head"><div>{title && <h2>{title}</h2>}{description && <p className="ik-hint">{description}</p>}</div>{actions}</div>}<div className="ik-panel-body">{children}</div></section>;
}
export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <header className="ik-page-header"><div>{eyebrow && <p className="ik-eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="ik-actions">{actions}</div>}</header>;
}
export function Toolbar({ children, className, ...props }: HTMLAttributes<HTMLDivElement>) { return <div {...props} className={cx("ik-toolbar", className)}>{children}</div>; }
