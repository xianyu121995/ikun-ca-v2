import type { AppShellProps } from "../src/index.js";

/** Keep the approved page's content and its CSS context, with one outer navigation. */
export function EmbeddedAppShell({ children }: AppShellProps) {
  return <div className="ik-theme review-embedded-shell"><div className="ik-main">{children}</div></div>;
}
