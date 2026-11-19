import {AppShell} from '@ikun/ui';
import {requireAuthPage} from '../../../lib/auth';
import {projectsAuth} from '../../../lib/projects';
import {presentRadar} from '../../../lib/radar-view';
import {WorkspaceLink} from '../../../components/auth/forms';
import {RadarBoard} from '../../../features/radar/radar-board';
import {SAMPLE_WIRE} from '../../../features/radar/sample';

export const dynamic = 'force-dynamic';

export default async function RadarPreviewPage() {
  projectsAuth();
  const session = await requireAuthPage('/prototypes/radar');
  const model = presentRadar(SAMPLE_WIRE, 1763510400);
  if (!model) return null;
  return <AppShell pathname="/prototypes/radar" LinkComponent={WorkspaceLink} account={{name: session.username, detail: '预览'}}>
    <RadarBoard model={model}/>
  </AppShell>;
}
