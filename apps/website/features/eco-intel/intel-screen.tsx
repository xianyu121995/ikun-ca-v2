'use client';

import Link from 'next/link';
import { AppShell } from '@ikun/ui';
import { WorkspaceLink } from '../../components/auth/forms';
import { ProjectsPanel } from './projects-panel';
import s from './intel.module.css';
import { TweetsPanel } from './tweets-panel';

const sections = [
  { id: 'projects', href: '/intel', label: '创始人关注的项目' },
  { id: 'tweets', href: '/intel/tweets', label: '种子/创始人账号推文' },
] as const;

export type IntelSection = (typeof sections)[number]['id'];

export function IntelScreen({ section, session }: {
  section: IntelSection;
  session: { username: string; role: 'superadmin' | 'user'; csrf_token: string; must_change_password: boolean };
}) {
  const canWrite = session.role === 'superadmin' && !session.must_change_password;
  return <AppShell pathname="/intel" LinkComponent={WorkspaceLink} account={{ name: session.username, detail: canWrite ? '可编辑' : '只读', href: '/auth' }}>
    <div className={s.page}>
      <header className="ik-page-header"><div>
        <p className="ik-eyebrow">工作台</p>
        <h1>生态情报</h1>
        <p>创始人新关注里的协议、发射台和黑客松，以及种子账号的推文。与猎手监控分开存放。</p>
      </div></header>
      <nav className={s.subnav} aria-label="生态情报分区">{sections.map(item => <Link key={item.id} href={item.href} aria-current={item.id === section ? 'page' : undefined}>{item.label}</Link>)}</nav>
      {section === 'projects' && <ProjectsPanel csrf={session.csrf_token} canWrite={canWrite} />}
      {section === 'tweets' && <TweetsPanel csrf={session.csrf_token} canWrite={canWrite} />}
    </div>
  </AppShell>;
}
