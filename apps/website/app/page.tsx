import {AppShell} from '@ikun/ui';
import '@ikun/ui/styles.css';
import {requireAuthPage} from '../lib/auth';
import {projectsAuth} from '../lib/projects';
import {headers} from 'next/headers';
import {getSession} from '../../../modules/auth/dist/src/server.js';
import {LogoutButton,WorkspaceLink} from '../components/auth/forms';
import ProjectsHome from '../components/projects-home';
export const dynamic='force-dynamic';
export default async function Page(){
  projectsAuth();const account=await requireAuthPage('/');
  const session=getSession(new Request(new URL('/api/v1/auth/me',process.env.IKUN_AUTH_ORIGIN),{headers:await headers()}));
  const writable=session.role==='superadmin'&&!session.must_change_password;
  // Owner 2026-10-19: user menu + edit mode move to the bottom-left of the sidebar (above the voice button).
  const footer=<details className="hpv2-usermenu"><summary>👤 {account.username} · {writable?'可编辑':'只读'}</summary><div className="hpv2-usermenu-pop"><a href="/auth/password">修改本人密码</a><LogoutButton/></div></details>;
  return <div className="hpv2-preview"><AppShell pathname="/" LinkComponent={WorkspaceLink} footer={footer}>
    <ProjectsHome userId={session.user_id} csrf={session.csrf_token} context={{mode:'live',role:session.role,capabilities:{can_edit_projects:writable}}}/></AppShell></div>;
}
