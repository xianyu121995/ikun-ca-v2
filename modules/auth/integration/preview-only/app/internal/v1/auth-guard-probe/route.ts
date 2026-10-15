import { withAuth } from '../../../../../../modules/auth/dist/src/server.js';
export const runtime='nodejs';
export const dynamic='force-dynamic';
const handler=(request:Request)=>withAuth(request,principal=>Response.json({fixture:true,role:principal.role}));
export const GET=handler;
export const POST=handler;
export const PATCH=handler;
export const DELETE=handler;
