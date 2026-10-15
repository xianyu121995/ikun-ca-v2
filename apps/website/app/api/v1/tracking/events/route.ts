import { trackingEventsRoute } from '../../../../../lib/tracking';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
import { projectsAuth } from '../../../../../lib/projects';
export function GET(request: Request) { projectsAuth(); return trackingEventsRoute(request); }
