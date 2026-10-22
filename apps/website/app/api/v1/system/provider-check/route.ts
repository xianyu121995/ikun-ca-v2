import {withAuth,requireSuperadmin} from '../../../../../../../modules/auth/dist/src/server.js';
import {trackingService} from '../../../../../lib/tracking';
export const dynamic='force-dynamic';
export async function POST(request:Request){return withAuth(request,async()=>{
 requireSuperadmin(request);
 return trackingService('provider-check',crypto.randomUUID(),{method:'POST',body:'{}',signal:request.signal});
});}
