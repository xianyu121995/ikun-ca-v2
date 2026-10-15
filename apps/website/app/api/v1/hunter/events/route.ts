import {projectsAuth} from '../../../../../lib/projects';
import {hunterEventsRoute} from '../../../../../lib/hunter';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export function GET(request:Request){projectsAuth();return hunterEventsRoute(request);}
