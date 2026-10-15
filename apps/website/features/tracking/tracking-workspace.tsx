"use client";
import { Children, cloneElement, isValidElement } from "react";
import { AppShell, Badge, type NavigationLinkProps } from "@ikun/ui";
import "@ikun/ui/styles.css";
import { TrackingPage } from "./final/tracking-page";
import { FinalTrackingDemo } from "./final/tracking-demo";
import s from "./final/tracking-page.module.css";

function PageLink({ href, children, ...props }: NavigationLinkProps) {
  const tracking = href === "/tracking";
  return <a {...props} href={href} {...(tracking ? { "aria-label": "猎手项目追踪", title: "猎手项目追踪" } : {})}>{tracking ? Children.map(children, child => isValidElement(child) && child.type === "span" ? cloneElement(child, {}, "猎手项目追踪") : child) : children}</a>;
}

export function TrackingWorkspace({ demo }: { demo: boolean }) {
  return <div className={s.workspace}><AppShell pathname="/tracking" LinkComponent={PageLink} footer={<><Badge tone="warning">UI 原型模式</Badge><p>纯演示数据 / 离线交互<br />不连接真实 API 或数据库</p></>}>{demo ? <FinalTrackingDemo /> : <TrackingPage mode="live" accounts={[]} posts={[]} />}</AppShell></div>;
}
