import {withAuth} from '../../../../../../modules/auth/dist/src/server.js';
import {projectsAuth,failure,requestId} from '../../../../lib/projects';
export const runtime='nodejs';
export const dynamic='force-dynamic';
function unavailable(request:Request){projectsAuth();return withAuth(request,async()=>failure(requestId(request),501,'NOT_IMPLEMENTED','此业务尚未接入测试站'));}
export const GET=unavailable;export const POST=unavailable;export const PUT=unavailable;export const PATCH=unavailable;export const DELETE=unavailable;
