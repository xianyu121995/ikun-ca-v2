'use client';
import { Children, cloneElement, isValidElement, type ReactNode } from 'react';
import { AppShell, type NavigationLinkProps } from '@ikun/ui';
import s from '../features/tracking/final/tracking-page.module.css';
function PageLink({ href, children, ...props }: NavigationLinkProps) { const tracking = href === '/tracking'; return <a {...props} href={href} {...(tracking ? { 'aria-label': '猎手项目追踪', title: '猎手项目追踪' } : {})}>{tracking ? Children.map(children, child => isValidElement(child) && child.type === 'span' ? cloneElement(child, {}, '猎手项目追踪') : child) : children}</a>; }
export function TrackingShell({ children }: {
    children: ReactNode;
}) { return <div className={s.workspace}><AppShell pathname='/tracking' LinkComponent={PageLink}>{children}</AppShell></div>; }
