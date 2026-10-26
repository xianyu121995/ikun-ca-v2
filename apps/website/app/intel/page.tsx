import { IntelScreen } from '../../features/eco-intel/intel-screen';
import { requireAuthPage } from '../../lib/auth';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export default async function IntelSeedsPage() {
  const session = await requireAuthPage('/intel');
  return <IntelScreen section="seeds" session={session} />;
}
