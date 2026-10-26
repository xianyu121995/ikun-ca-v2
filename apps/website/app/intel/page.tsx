import { IntelScreen } from '../../features/eco-intel/intel-screen';
import { requireAuthPage } from '../../lib/auth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export default async function IntelProjectsPage() {
  const session = await requireAuthPage('/intel');
  return <IntelScreen section="projects" session={session} />;
}
