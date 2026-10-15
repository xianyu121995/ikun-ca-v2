import { createHash } from 'node:crypto';
import { requireIdentity, requireSuperadmin, withAuth } from '../../../modules/auth/dist/src/server.js';
import { ipc, requestId, failure } from './projects';
const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
export function commandId(actor: string, route: string, key: string) { const bytes = createHash('sha256').update(JSON.stringify([actor, 'ikun-main', route, key])).digest().subarray(0, 16); bytes[6] = (bytes[6]! & 15) | 64; bytes[8] = (bytes[8]! & 63) | 128; const h = bytes.toString('hex'); return 'cmd_' + [h.slice(0, 8), h.slice(8, 12), h.slice(12, 16), h.slice(16, 20), h.slice(20)].join('-'); }
export async function trackingService(path: string, id: string, options: RequestInit = {}) {
    const target = process.env.TRACKING_API_URL, token = process.env.TRACKING_API_TOKEN;
    if (!target || !token || token.length < 32)
        return failure(id, 503, 'AUTH_NOT_CONFIGURED', 'Tracking 未配置');
    let url: URL;
    try {
        url = new URL(target);
    }
    catch {
        return failure(id, 503, 'AUTH_NOT_CONFIGURED', 'Tracking 目标无效');
    }
    if (url.protocol !== 'http:' || !['127.0.0.1', '[::1]'].includes(url.hostname) || url.pathname !== '/' || url.username || url.password || url.search || url.hash)
        return failure(id, 503, 'AUTH_NOT_CONFIGURED', 'Tracking 目标无效');
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 5000);
    try {
        const response = await fetch(url.origin + '/internal/v1/' + path, { ...options, headers: { 'authorization': 'Bearer ' + token, 'content-type': 'application/json', 'x-request-id': id, ...options.headers }, cache: 'no-store', redirect: 'error', signal: options.signal ? AbortSignal.any([options.signal, controller.signal]) : controller.signal });
        return new Response(response.body, { status: response.status, headers: new Headers(response.headers) });
    }
    catch {
        return failure(id, 503, 'UPSTREAM_UNAVAILABLE', '操作结果待核对，请查询原 command_id');
    }
    finally {
        clearTimeout(timer);
    }
}
async function readBody(request: Request, empty = false) {
    const reader = request.body?.getReader();
    if (!reader) {
        if (empty)
            return {};
        throw Error('BODY');
    }
    let length = 0;
    const parts: Uint8Array[] = [];
    const until = Date.now() + 5000;
    try {
        while (true) {
            let timer: ReturnType<typeof setTimeout> | undefined;
            const part = await Promise.race([reader.read(), new Promise<never>((_, reject) => { timer = setTimeout(() => reject(Error('TIMEOUT')), Math.max(1, until - Date.now())); })]).finally(() => clearTimeout(timer));
            if (part.done)
                break;
            length += part.value.length;
            if (length > 65536)
                throw Error('SIZE');
            parts.push(part.value);
        }
        if (!length && empty)
            return {};
        const body = JSON.parse(Buffer.concat(parts).toString());
        if (!body || typeof body !== 'object' || Array.isArray(body))
            throw Error('BODY');
        return body as Record<string, unknown>;
    }
    finally {
        void reader.cancel().catch(() => { });
        reader.releaseLock();
    }
}
export async function trackingRoute(original: Request) {
    const id = requestId(original);
    const headers = new Headers(original.headers);
    headers.set('x-request-id', id);
    const request = new Request(original, { headers });
    return withAuth(request, async () => {
        const method = request.method, read = ['GET', 'HEAD'].includes(method), principal = read ? requireIdentity(request) : requireSuperadmin(request);
        const url = new URL(request.url), suffix = url.pathname.slice('/api/v1/tracking'.length);
        if (read) {
            if (!new RegExp('^/(?:subscriptions(?:/sub_' + uuid + ')?|latest|activities)$').test(suffix))
                return failure(id, 404, 'NOT_FOUND', '路径不存在');
            const out = await trackingService(suffix.slice(1) + url.search, id, { signal: request.signal, headers: request.headers.has('last-event-id') ? { 'last-event-id': request.headers.get('last-event-id')! } : {} });
            return new Response(out.body, { status: out.status, headers: { 'content-type': out.headers.get('content-type') ?? 'application/json', 'cache-control': 'no-store', 'x-request-id': id, ...(out.headers.get('etag') ? { etag: out.headers.get('etag')! } : {}) } });
        }
        if (url.search)
            return failure(id, 422, 'VALIDATION_ERROR', '写入不接受查询字段');
        const key = request.headers.get('idempotency-key');
        if (!key || !new RegExp('^' + uuid + '$').test(key))
            return failure(id, 422, 'VALIDATION_ERROR', '需要 UUID Idempotency-Key');
        let body: Record<string, unknown>;
        try {
            body = await readBody(request, true);
        }
        catch {
            return failure(id, 422, 'VALIDATION_ERROR', '无效 JSON');
        }
        if (suffix === '/subscriptions' && method === 'POST') {
            if (Object.keys(body).some(k => !['project_id', 'name', 'x_user_id', 'x_handle', 'notes', 'confirmed'].includes(k)) || body.confirmed !== true || typeof body.project_id !== 'string')
                return failure(id, 422, 'VALIDATION_ERROR', '需要人工确认的项目');
            const canonical = await ipc({ operation: 'get', target: body.project_id, principal, request_id: id }, request.signal);
            if (!canonical.ok)
                return canonical;
            const record = (await canonical.json()).data;
            if (record.project_id !== body.project_id)
                return failure(id, 409, 'CONFLICT', 'canonical 引用不匹配');
            const command = { schema_version: 1, command_id: commandId(principal.user_id, method + ' ' + url.pathname, key), tenant_id: 'ikun-main', actor: principal, operation: 'tracking.create', project_id: body.project_id, subscription_id: null, expected_revision: null,
                payload: { name: body.name, x_user_id: body.x_user_id ?? null, x_handle: body.x_handle, notes: body.notes ?? '', confirmed: true }, issued_at: new Date().toISOString() };
            return trackingService('commands', id, { method: 'POST', body: JSON.stringify(command) });
        }
        const match = new RegExp('^/subscriptions/(sub_' + uuid + ')(?:/(start|stop|resume))?$').exec(suffix);
        if (!match || !['PATCH', 'DELETE', 'POST'].includes(method) || method === 'POST' && !match[2])
            return failure(id, 404, 'NOT_FOUND', '路径不存在');
        const revision = /^"rev-([1-9][0-9]*)"$/.exec(request.headers.get('if-match') ?? '');
        if (!revision)
            return failure(id, request.headers.has('if-match') ? 422 : 428, 'VALIDATION_ERROR', '需要有效 If-Match');
        if (method === 'PATCH')
            return trackingService('subscriptions/' + match[1], id, { method: 'PATCH', headers: { 'idempotency-key': key }, body: JSON.stringify({ actor: principal, expected_revision: Number(revision[1]), patch: body }) });
        if (Object.keys(body).length)
            return failure(id, 422, 'VALIDATION_ERROR', '状态操作不接受 body');
        const current = await trackingService('subscriptions/' + match[1], id);
        if (!current.ok)
            return current;
        const sub = (await current.json()).data;
        const command = { schema_version: 1, command_id: commandId(principal.user_id, method + ' ' + url.pathname, key), tenant_id: 'ikun-main', actor: principal, operation: 'tracking.' + (method === 'DELETE' ? 'remove' : match[2]), project_id: sub.project_id, subscription_id: match[1], expected_revision: Number(revision[1]), payload: {}, issued_at: new Date().toISOString() };
        return trackingService('commands', id, { method: 'POST', body: JSON.stringify(command) });
    });
}
/** Tracking-only candidate for the frozen website SSE gateway; never replaces B1's singleton. */
export async function trackingEventsRoute(original: Request) {
    const id = requestId(original), headers = new Headers(original.headers);
    headers.set('x-request-id', id);
    const request = new Request(original, { headers });
    return withAuth(request, async () => {
        requireIdentity(request);
        if (new URL(request.url).search)
            return failure(id, 422, 'VALIDATION_ERROR', '事件流不接受查询字段');
        const upstream = await trackingService('events', id, { signal: request.signal, headers: request.headers.has('last-event-id') ? { 'last-event-id': request.headers.get('last-event-id')! } : {} });
        return new Response(upstream.body, { status: upstream.status, headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json', 'cache-control': 'no-store', 'x-request-id': id } });
    });
}
