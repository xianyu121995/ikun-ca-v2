import { withAuth } from '../../../../../../../modules/auth/dist/src/server.js';
import { handleIntel } from '../../../../../lib/eco-intel/http';
import { intelStore } from '../../../../../lib/eco-intel/store';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function route(request: Request) {
  return withAuth(request, principal => handleIntel(intelStore(), principal, request));
}

export const GET = route;
export const POST = route;
export const PATCH = route;
export const DELETE = route;
