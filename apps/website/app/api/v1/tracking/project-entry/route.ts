import {projectTrackingRoute} from '../../../../../lib/project-tracking';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export function GET(request:Request){return projectTrackingRoute(request);}
export function POST(request:Request){return projectTrackingRoute(request);}
