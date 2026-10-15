import type { ReactNode } from 'react';
import { AppShell } from '@ikun/ui';
import '@ikun/ui/styles.css';
import { LogoutButton } from './forms';

/** No account prop: the shared sidebar has exactly its three business links. */
export function AuthShell({children,pathname,username}:{children:ReactNode;pathname:string;username:string}) {
  return <AppShell pathname={pathname}><header style={{display:'flex',justifyContent:'flex-end',alignItems:'center',gap:12,padding:'16px',flexWrap:'wrap'}}>
    <details><summary>用户菜单 · {username}</summary><div style={{display:"flex",gap:12,padding:12,alignItems:"center",flexWrap:"wrap"}}><a href="/auth/password">修改本人密码</a><LogoutButton /></div></details>
  </header><section style={{padding:'clamp(12px,3vw,32px)',maxWidth:900,margin:'0 auto'}}>{children}</section></AppShell>;
}
