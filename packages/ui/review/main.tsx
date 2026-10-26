import { Component, useCallback, useEffect, useState, type ErrorInfo, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import Home from "final-ui:home";
import Hunter from "final-ui:hunter";
import { TrackingWorkspace } from "final-ui:tracking";
import { AppShell, Badge, ErrorState, type NavigationLinkProps } from "../src/index.js";
import "../src/styles.css";
import "./unified.css";

const routes = ["/", "/hunter", "/tracking"] as const;
type Route = typeof routes[number];
const asRoute = (path: string): Route => routes.includes(path as Route) ? path as Route : "/";
class PageBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* No raw error or page data is logged. */ }
  render() { return this.state.failed ? <ErrorState title="页面预览未能加载" description="请刷新重试。当前是独立 UI 联调，不会影响真实监控。" onRetry={() => location.reload()} /> : this.props.children; }
}
function Review() {
  const [route, setRoute] = useState<Route>(() => asRoute(location.pathname));
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => { const pop = () => setRoute(asRoute(location.pathname)); window.addEventListener("popstate", pop); return () => window.removeEventListener("popstate", pop); }, []);
  const Link = useCallback(function ReviewLink({ href, children, ...props }: NavigationLinkProps) {
    return <a {...props} href={href} onClick={event => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      if (href === "/intel") { event.preventDefault(); setNotice("生态情报在网站 /intel，不在这三页定稿预览里。"); return; }
      if (!routes.includes(href as Route)) return;
      event.preventDefault();
      setNotice(null);
      if (location.pathname === href) return;
      history.pushState({}, "", href); setRoute(href as Route); window.scrollTo(0, 0);
    }}>{children}</a>;
  }, []);
  return <div className="ik-theme review-app"><AppShell pathname={route} LinkComponent={Link} footer={<div className="review-sidebar-note"><Badge tone="warning">定稿 UI 联调</Badge><p>演示数据 · 本地预览<br />切页或刷新会重置修改</p>{notice && <p>{notice}</p>}</div>}>
    <div className={`review-page review-page--${route === "/" ? "home" : route === "/hunter" ? "hunter" : "tracking"}`} data-review-route={route}>
      <PageBoundary key={route}>{route === "/" ? <Home /> : route === "/hunter" ? <Hunter /> : <TrackingWorkspace demo />}</PageBoundary>
    </div>
  </AppShell></div>;
}
const root = document.getElementById("root"); if (!root) throw new Error("Review root missing");
createRoot(root).render(<Review />);
