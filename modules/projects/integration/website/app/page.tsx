import {AppShell} from '@ikun/ui';
import '@ikun/ui/styles.css';
import {requireAuthPage} from '../lib/auth';
import {projectsAuth} from '../lib/projects';
import {headers} from 'next/headers';
import {getSession} from '../../../modules/auth/dist/src/server.js';
import {LogoutButton} from '../components/auth/forms';
import ProjectsHome from '../components/projects-home';
export const dynamic='force-dynamic';
export default async function Page(){
  projectsAuth();const account=await requireAuthPage('/');
  const session=getSession(new Request(new URL('/api/v1/auth/me',process.env.IKUN_AUTH_ORIGIN),{headers:await headers()}));
  return <div className="hpv2-preview"><AppShell pathname="/"><header style={{display:'flex',justifyContent:'flex-end',gap:12,padding:16}}><details><summary>用户菜单 · {account.username}</summary><div style={{display:'flex',gap:12,padding:12}}><a href="/auth/password">修改本人密码</a><LogoutButton/></div></details></header>
    <ProjectsHome userId={session.user_id} csrf={session.csrf_token} context={{mode:'live',role:session.role,capabilities:{can_edit_projects:session.role==='superadmin'&&!session.must_change_password}}}/></AppShell></div>;
}
