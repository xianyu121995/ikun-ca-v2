import {withAuth} from '../../../../../../../modules/auth/dist/src/server.js';
import {projectsAuth,failure,requestId} from '../../../../../lib/projects';
export const runtime='nodejs';
export const dynamic='force-dynamic';
// B3 is not received. Never substitute Projects/Hunter frames for this module.
export function GET(request:Request){projectsAuth();return withAuth(request,async()=>failure(requestId(request),501,'NOT_IMPLEMENTED','Tracking 尚未接入'));}
