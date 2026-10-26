'use client';

import Link from 'next/link';
import { AppShell } from '@ikun/ui';
import { WorkspaceLink } from '../../components/auth/forms';
import { FollowsPanel } from './follows-panel';
import s from './intel.module.css';
import { SeedsPanel } from './seeds-panel';
import { TweetsPanel } from './tweets-panel';

const sections = [
  { id: 'seeds', href: '/intel', label: '种子账号' },
  { id: 'tweets', href: '/intel/tweets', label: '种子推文' },
  { id: 'follows', href: '/intel/follows', label: '新关注' },
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
        <p>官方、创始人和发射台种子的推文与新关注。与猎手监控分开存放。</p>
      </div></header>
      <nav className={s.subnav} aria-label="生态情报分区">{sections.map(item => <Link key={item.id} href={item.href} aria-current={item.id === section ? 'page' : undefined}>{item.label}</Link>)}</nav>
      {section === 'seeds' && <SeedsPanel csrf={session.csrf_token} canWrite={canWrite} />}
      {section === 'tweets' && <TweetsPanel csrf={session.csrf_token} canWrite={canWrite} />}
      {section === 'follows' && <FollowsPanel csrf={session.csrf_token} canWrite={canWrite} />}
    </div>
  </AppShell>;
}
