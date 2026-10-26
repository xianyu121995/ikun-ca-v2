import { IntelScreen } from '../../../features/eco-intel/intel-screen';
import { requireAuthPage } from '../../../lib/auth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export default async function IntelFollowsPage() {
  const session = await requireAuthPage('/intel/follows');
  return <IntelScreen section="follows" session={session} />;
}
