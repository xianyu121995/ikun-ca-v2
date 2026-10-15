import type {Metadata} from 'next';
import '@ikun/ui/styles.css';
import './globals.css';
export const metadata:Metadata={title:'ikun.ca v2',description:'受保护的 v2 测试站'};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="zh-CN"><body>{children}</body></html>;}
