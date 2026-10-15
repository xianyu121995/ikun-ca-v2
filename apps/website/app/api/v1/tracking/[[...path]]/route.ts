import { trackingRoute } from '../../../../../lib/tracking';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
import { projectsAuth } from '../../../../../lib/projects';
function route(request: Request) { projectsAuth(); return trackingRoute(request); }
export const GET = route;
export const POST = route;
export const PATCH = route;
export const DELETE = route;
