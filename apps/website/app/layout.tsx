import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "ikun.ca v2", description: "全新重建项目 · 基础架构" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
