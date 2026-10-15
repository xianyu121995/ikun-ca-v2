import { withAuth, requireIdentity } from '../../../../../../../modules/auth/dist/src/server.js';
import { projectsRoute, requestId } from '../../../../../lib/projects';
import { trackingService } from '../../../../../lib/tracking';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
    return withAuth(request, async () => {
        requireIdentity(request);
        const prior = await projectsRoute(request);
        if (prior.status !== 404)
            return prior;
        const value = await prior.clone().json();
        if (value.error?.code !== 'NOT_FOUND')
            return prior;
        return trackingService('commands/' + new URL(request.url).pathname.split('/').at(-1), requestId(request));
    });
}
