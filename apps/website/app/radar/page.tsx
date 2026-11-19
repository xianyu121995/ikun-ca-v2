import {AppShell} from '@ikun/ui';
import {requireAuthPage} from '../../lib/auth';
import {projectsAuth} from '../../lib/projects';
import {WorkspaceLink} from '../../components/auth/forms';
import {RadarLive} from '../../features/radar/radar-live';

export const dynamic = 'force-dynamic';

export default async function RadarPage() {
  projectsAuth();
  const session = await requireAuthPage('/radar');
  return <AppShell pathname="/radar" LinkComponent={WorkspaceLink} account={{name: session.username, detail: session.role === 'superadmin' ? '超级管理员' : '只读'}}>
    <RadarLive userId={session.user_id}/>
  </AppShell>;
}
