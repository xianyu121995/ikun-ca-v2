// Server-only BFF factory. The website owner injects the REAL session policy.
// Mount handler as app/api/hunterradar/v1/[...path]/route.ts exports.
type Capability = 'hunter.read' | 'hunter.read_raw' | 'hunter.manage';
type Actor = { id: string; role: 'user' | 'superadmin' };
type Policy = (request: Request, capability: Capability) => Promise<Actor | null>;
type Config = { upstream: string; adminToken: string; viewToken: string };

export function createHunterGateway(authorize: Policy, config: Config) {
  const service = new URL(config.upstream);
  if (service.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(service.hostname)
      || service.pathname !== '/' || service.username || service.password || service.search || service.hash
      || Math.min(config.adminToken.length, config.viewToken.length) < 32 || config.adminToken === config.viewToken) {
    throw new Error('invalid_hunter_gateway_configuration');
  }
  return async function handler(request: Request, context: { params: Promise<{ path: string[] }> }) {
    const fail = (code: string, status: number) => Response.json({ error: code }, { status });
    const { path } = await context.params;
    if (!path?.length || path.some(p => !/^[a-zA-Z0-9_.-]+$/.test(p) || p === '.' || p === '..')
        || !['page','assets','session','status','signals','aggregate','hunters','discoveries','tasks'].includes(path[0])) return fail('not_found', 404);
    const write = request.method !== 'GET';
    const capability = write ? 'hunter.manage' : path[0] === 'hunters' ? 'hunter.read_raw' : 'hunter.read';
    const actor = await authorize(request, capability);
    if (!actor) return fail('hunter_permission_required', 403);
    const manager = await authorize(request, 'hunter.manage');
    if ((write || path[0] === 'hunters') && manager?.role !== 'superadmin') return fail('hunter_admin_required', 403);
    const origin = request.headers.get('origin');
    if (write && origin && origin !== new URL(request.url).origin) return fail('cross_origin_mutation_rejected', 403);
    const body = write ? await request.arrayBuffer() : undefined;
    if (body && body.byteLength > 65536) return fail('request_too_large', 413);
    const target = new URL('/api/hunterradar/v1/'+path.join('/'), service);
    target.search = new URL(request.url).search;
    const headers: Record<string,string> = {
      Authorization: 'Bearer '+(manager?.role === 'superadmin' ? config.adminToken : config.viewToken),
      'X-HunterRadar-Actor': actor.id,
      'Content-Type': request.headers.get('content-type') || 'application/json',
    };
    const key = request.headers.get('idempotency-key');
    if (key) headers['Idempotency-Key'] = key;
    try {
      const result = await fetch(target, { method: request.method, headers, body,
        redirect: 'error', signal: AbortSignal.timeout(20000), cache: 'no-store' });
      const safe = new Headers();
      for (const key of ['content-type','cache-control','content-security-policy','x-content-type-options','referrer-policy']) {
        const value = result.headers.get(key); if (value) safe.set(key, value);
      }
      return new Response(result.body, { status: result.status, headers: safe });
    } catch {
      return fail('hunter_service_unavailable', 503);
    }
  };
}
