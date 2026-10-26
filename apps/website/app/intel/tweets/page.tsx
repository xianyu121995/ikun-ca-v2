import { IntelScreen } from '../../../features/eco-intel/intel-screen';
import { requireAuthPage } from '../../../lib/auth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export default async function IntelTweetsPage() {
  const session = await requireAuthPage('/intel/tweets');
  return <IntelScreen section="tweets" session={session} />;
}
