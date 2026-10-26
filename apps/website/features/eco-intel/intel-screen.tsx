'use client';

import Link from 'next/link';
import { AppShell } from '@ikun/ui';
import { WorkspaceLink } from '../../components/auth/forms';
import { ProjectsPanel } from './projects-panel';
import { TweetsPanel } from './tweets-panel';
import '../hunter-discovery/v3/v3.css';
import './surface.css';

const sections = [
  { id: 'projects', href: '/intel', label: '创始人关注' },
  { id: 'tweets', href: '/intel/tweets', label: '种子推文' },
] as const;

export type IntelSection = (typeof sections)[number]['id'];

export function IntelScreen({ section, session }: {
  section: IntelSection;
  session: { username: string; role: 'superadmin' | 'user'; csrf_token: string; must_change_password: boolean };
}) {
  const canWrite = session.role === 'superadmin' && !session.must_change_password;
  return <div className="hunter-v3">
    <AppShell pathname="/intel" LinkComponent={WorkspaceLink} account={{ name: session.username, detail: canWrite ? '可编辑' : '只读', href: '/auth' }} footer={<>
      <div className="nav-hint">创始人新关注 → 本地分类 → 人工确认后再项目追踪</div>
      <div className="side-bottom"><strong><span className="live-dot" />生态情报</strong><p>分类在本地<br />不连接 6551</p></div>
    </>}>
      <div className="main">
        {section === 'projects'
          ? <ProjectsPanel csrf={session.csrf_token} canWrite={canWrite} switcher={<Switcher section={section} />} />
          : <TweetsPanel csrf={session.csrf_token} canWrite={canWrite} switcher={<Switcher section={section} />} />}
      </div>
    </AppShell>
  </div>;
}

function Switcher({ section }: { section: IntelSection }) {
  return <div className="title-buttons">{sections.map(item => <Link key={item.id} href={item.href} aria-current={item.id === section ? 'page' : undefined}>{item.label}</Link>)}</div>;
}
