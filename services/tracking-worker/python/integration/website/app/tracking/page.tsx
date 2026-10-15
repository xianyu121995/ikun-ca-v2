import { TrackingShell } from '../../components/tracking-shell';
import '@ikun/ui/styles.css';
import { requireAuthPage } from '../../lib/auth';
import { TrackingLive } from '../../components/tracking-live';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export default async function Tracking() { const identity = await requireAuthPage('/tracking'); return <TrackingShell><TrackingLive fixture={process.env.IKUN_TRACKING_FIXTURE==='1'} username={identity.username} csrf={identity.csrf_token} canManage={identity.role === 'superadmin' && !identity.must_change_password}/></TrackingShell>; }
