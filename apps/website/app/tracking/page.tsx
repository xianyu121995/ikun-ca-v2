import { TrackingShell } from '../../components/tracking-shell';
import '@ikun/ui/styles.css';
import { requireAuthPage } from '../../lib/auth';
import { TrackingLive } from '../../components/tracking-live';
import { headers } from 'next/headers';
import { randomUUID } from 'node:crypto';
import { auth } from '../../../../modules/auth/dist/src/server.js';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export default async function Tracking() {
  const identity = await requireAuthPage('/tracking');
  const http = auth();
  const actor = http.authorize(new Request(new URL('/tracking', http.store.cfg.origin), { headers: await headers() }), false);
  return <TrackingShell><TrackingLive fixture={process.env.IKUN_TRACKING_FIXTURE==='1'} username={identity.username} csrf={identity.csrf_token}
    voiceSession={{ user_id: actor.id, role: actor.role, epoch: randomUUID() }}
    canManage={identity.role === 'superadmin' && !identity.must_change_password}/></TrackingShell>;
}
