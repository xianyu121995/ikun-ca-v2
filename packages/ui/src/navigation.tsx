"use client";

import type { AnchorHTMLAttributes, ComponentType, ReactNode } from "react";
import { Icon, type IconName } from "./icons.js";
import { cx } from "./primitives.js";

// Phase-two presentation routes; these do not create business pages.
export const BUSINESS_NAVIGATION: ReadonlyArray<{ href: string; label: string; icon: IconName }> = [
  { href: "/", label: "主页", icon: "home" },
  { href: "/hunter", label: "猎手监控", icon: "radar" },
  { href: "/tracking", label: "猎手项目监控", icon: "layers" },
];
export function isNavigationActive(pathname: string, href: string): boolean {
  const path = pathname.split(/[?#]/)[0]?.replace(/\/+$/, "") || "/";
  return href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
}
export type NavigationLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { href: string };
export interface AppShellProps {
  pathname: string;
  children: ReactNode;
  account?: { name: string; detail?: string; href?: string };
  footer?: ReactNode;
  LinkComponent?: ComponentType<NavigationLinkProps>;
}
function NativeLink(props: NavigationLinkProps) { return <a {...props} />; }
export function AppShell({ pathname, children, account, footer, LinkComponent = NativeLink }: AppShellProps) {
  return <div className="ik-theme ik-shell">
    <a className="ik-skip-link" href="#ik-main">跳到主内容</a>
    <aside className="ik-sidebar">
      <LinkComponent href="/" className="ik-brand" aria-label="ikun.ca 主页"><span className="ik-brand-mark" aria-hidden="true">ik</span><span className="ik-brand-text">ikun<span>.ca</span><small>WEB3 TERMINAL</small></span></LinkComponent>
      <div className="ik-nav-label">工作空间</div>
      <nav className="ik-nav" aria-label="业务导航">{BUSINESS_NAVIGATION.map(item => <LinkComponent key={item.href} href={item.href} className={cx("ik-nav-link", isNavigationActive(pathname, item.href) && "is-active")} aria-current={isNavigationActive(pathname, item.href) ? "page" : undefined} aria-label={item.label} title={item.label}><Icon name={item.icon} /><span>{item.label}</span><Icon className="ik-nav-arrow" name="chevron" /></LinkComponent>)}</nav>
      <div className="ik-sidebar-bottom">{footer && <div className="ik-sidebar-footer">{footer}</div>}{account && <LinkComponent href={account.href ?? "/auth"} className="ik-account-link" aria-label={`账号管理：${account.name}`} title={`账号管理：${account.name}`}><span className="ik-avatar" aria-hidden="true">{Array.from(account.name)[0]?.toUpperCase() ?? "?"}</span><span className="ik-account-text"><strong>{account.name}</strong><small>{account.detail ?? "账号管理"}</small></span><Icon name="chevron" /></LinkComponent>}</div>
    </aside>
    <main className="ik-main" id="ik-main" tabIndex={-1}>{children}</main>
  </div>;
}
