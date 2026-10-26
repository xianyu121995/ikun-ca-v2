'use client';

import { useRouter } from 'next/navigation';
import { AppShell, Button } from '@ikun/ui';
import { WorkspaceLink } from '../../components/auth/forms';
import { ProjectsPanel } from './projects-panel';
import { TweetsPanel } from './tweets-panel';
import track from '../tracking/final/tracking-page.module.css';
import '../hunter-discovery/v3/v3.css';

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
  const switcher = <SectionSwitcher section={section} />;
  if (section === 'tweets') {
    return <div className={track.workspace}>
      <AppShell pathname="/intel" LinkComponent={WorkspaceLink} account={{ name: session.username, detail: canWrite ? '可编辑' : '只读', href: '/auth' }} footer={<>
        <div className="nav-hint">种子推文按本地关键词归档，不连接 6551</div>
        <div className="side-bottom"><strong><span className="live-dot" />生态情报</strong><p>分类在本地<br />不连接 6551</p></div>
      </>}>
        <TweetsPanel csrf={session.csrf_token} canWrite={canWrite} username={session.username} switcher={switcher} />
      </AppShell>
    </div>;
  }
  return <div className="hunter-v3">
    <AppShell pathname="/intel" LinkComponent={WorkspaceLink} account={{ name: session.username, detail: canWrite ? '可编辑' : '只读', href: '/auth' }} footer={<>
      <div className="nav-hint">创始人新关注 → 本地分类 → 人工确认后再项目追踪</div>
      <div className="side-bottom"><strong><span className="live-dot" />生态情报</strong><p>分类在本地<br />不连接 6551</p></div>
    </>}>
      <div className="main">
        <ProjectsPanel csrf={session.csrf_token} canWrite={canWrite} switcher={switcher} />
      </div>
    </AppShell>
  </div>;
}

function SectionSwitcher({ section }: { section: IntelSection }) {
  const router = useRouter();
  return <>{sections.map(item => {
    const current = item.id === section;
    return <Button key={item.id} variant={section === 'tweets' && current ? 'primary' : 'secondary'} className={current ? 'soft' : ''} aria-current={current ? 'page' : undefined} onClick={() => { if (!current) router.push(item.href); }}>{item.label}</Button>;
  })}</>;
}
