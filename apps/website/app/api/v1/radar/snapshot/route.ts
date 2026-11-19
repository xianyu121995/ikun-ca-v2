import {randomUUID} from 'node:crypto';
import {withAuth} from '../../../../../../../modules/auth/dist/src/server.js';
import {projectsAuth} from '../../../../../lib/projects';
import {radarSnapshot} from '../../../../../lib/radar-bridge';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function requestId(request: Request) {
  const value = request.headers.get('x-request-id');
  return value && /^[A-Za-z0-9_-]{1,64}$/.test(value) ? value : randomUUID();
}

export function GET(original: Request) {
  projectsAuth();
  const id = requestId(original);
  if (new URL(original.url).search) {
    return Response.json({error: {code: 'VALIDATION_ERROR', message: '雷达快照不接受查询参数', retryable: false}, request_id: id}, {status: 422, headers: {'cache-control': 'no-store'}});
  }
  return withAuth(original, async () => radarSnapshot(id));
}
