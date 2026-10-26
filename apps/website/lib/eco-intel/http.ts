import { createHash, randomUUID } from 'node:crypto';
import { IntelError } from './rules';
import type { IntelStore } from './store';
import type { IntelPrincipal } from './types';

function requestIdOf(request: Request): string {
  const value = request.headers.get('x-request-id');
  return value && /^[A-Za-z0-9_-]{1,64}$/.test(value) ? value : randomUUID();
}

function json(requestId: string, status: number, payload: Record<string, unknown>): Response {
  return Response.json({ ...payload, request_id: requestId }, {
    status,
    headers: { 'cache-control': 'no-store', 'x-request-id': requestId, 'x-content-type-options': 'nosniff' },
  });
}

function fail(requestId: string, status: number, code: string, message: string): Response {
  return json(requestId, status, { error: { code, message, retryable: status === 503 } });
}

function ok(requestId: string, status: number, data: unknown): Response {
  return json(requestId, status, { data });
}

async function readRaw(request: Request): Promise<string> {
  const reader = request.body?.getReader();
  if (!reader) return '';
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      size += next.value.byteLength;
      if (size > 16384) throw new IntelError(413, 'VALIDATION_ERROR', '请求过大');
      chunks.push(next.value);
    }
  } catch (error) {
    if (error instanceof IntelError) throw error;
    throw new IntelError(422, 'VALIDATION_ERROR', '请求体无法读取');
  }
  return Buffer.concat(chunks).toString('utf8');
}

function parseObject(raw: string): Record<string, unknown> {
  if (!raw) return {};
  let data: unknown;
  try { data = JSON.parse(raw); } catch { throw new IntelError(422, 'VALIDATION_ERROR', '请求 JSON 无效'); }
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new IntelError(422, 'VALIDATION_ERROR', '请求 JSON 必须是对象');
  return data as Record<string, unknown>;
}

function onlyKeys(body: Record<string, unknown>, allowed: readonly string[]) {
  for (const key of Object.keys(body)) {
    if (!allowed.includes(key)) throw new IntelError(422, 'VALIDATION_ERROR', `不能提交字段 ${key}`);
  }
}

function limitOf(url: URL): number {
  const raw = url.searchParams.get('limit');
  if (raw === null || raw === '') return 50;
  if (!/^\d+$/.test(raw)) throw new IntelError(422, 'VALIDATION_ERROR', 'limit 无效');
  const value = Number(raw);
  if (value < 1 || value > 100) throw new IntelError(422, 'VALIDATION_ERROR', 'limit 必须在 1 到 100 之间');
  return value;
}

function searchOf(url: URL): string {
  const value = (url.searchParams.get('q') ?? '').trim();
  if (value.length > 80) throw new IntelError(422, 'VALIDATION_ERROR', '搜索过长');
  return value;
}

function idempotencyKey(request: Request): string {
  const key = request.headers.get('idempotency-key');
  if (!key || !/^[A-Za-z0-9_-]{8,80}$/.test(key)) throw new IntelError(422, 'VALIDATION_ERROR', '缺少有效的 Idempotency-Key');
  return key;
}

function expectedRevision(request: Request): number {
  const header = request.headers.get('if-match');
  const match = header?.match(/^"rev-(\d+)"$/) ?? header?.match(/^rev-(\d+)$/);
  if (!match) throw new IntelError(422, 'VALIDATION_ERROR', '缺少 If-Match 版本');
  const revision = Number(match[1]);
  if (!Number.isSafeInteger(revision) || revision < 1) throw new IntelError(422, 'VALIDATION_ERROR', 'If-Match 版本无效');
  return revision;
}

/**
 * Read/write API for the eco-intel skeleton.
 * TODO(6551): do not add a live WSS client here. Provider events belong in acceptProviderEvent().
 */
export async function handleIntel(store: IntelStore, principal: IntelPrincipal, request: Request): Promise<Response> {
  const requestId = requestIdOf(request);
  try {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/api\/v1\/intel\/(seeds|tweets|follows)(?:\/([A-Za-z0-9_-]+)(?:\/(promote))?)?$/);
    if (!match) return fail(requestId, 404, 'NOT_FOUND', '生态情报入口不存在');
    const collection = match[1] as 'seeds' | 'tweets' | 'follows';
    const id = match[2];
    const action = match[3];
    const method = request.method;
    if (method === 'GET' || method === 'HEAD') {
      if (id) return fail(requestId, 404, 'NOT_FOUND', '生态情报入口不存在');
      return ok(requestId, 200, readList(store, collection, url));
    }
    if (principal.role !== 'superadmin') return fail(requestId, 403, 'FORBIDDEN', '当前账号只读');
    if (!['POST', 'PATCH', 'DELETE'].includes(method)) return fail(requestId, 405, 'VALIDATION_ERROR', '不支持的方法');
    const raw = await readRaw(request);
    const body = parseObject(raw);
    const key = idempotencyKey(request);
    const hash = createHash('sha256').update(raw).digest('hex');
    const route = `${method} ${url.pathname}`;
    const outcome = store.transaction(() => {
      const prior = store.recall(principal.user_id, route, key);
      if (prior) {
        if (prior.body_hash !== hash) throw new IntelError(409, 'CONFLICT', '原请求结果与当前内容不一致');
        return { status: prior.status, body: prior.body };
      }
      const written = write(store, method, collection, id, action, body, request);
      store.remember(principal.user_id, route, key, hash, written.status, 'data', written.body);
      return written;
    });
    return ok(requestId, outcome.status, outcome.body);
  } catch (error) {
    if (error instanceof IntelError) return fail(requestId, error.status, error.code, error.message);
    return fail(requestId, 500, 'INTERNAL_ERROR', '生态情报请求未完成');
  }
}

function readList(store: IntelStore, collection: 'seeds' | 'tweets' | 'follows', url: URL) {
  const limit = limitOf(url);
  const q = searchOf(url);
  const cursor = url.searchParams.get('cursor') ?? undefined;
  if (collection === 'seeds') return store.listSeeds(q, limit, cursor);
  if (collection === 'tweets') return store.listTweets(q, limit, cursor);
  return store.listFollows(q, url.searchParams.get('status') ?? '', limit, cursor);
}

function write(store: IntelStore, method: string, collection: 'seeds' | 'tweets' | 'follows', id: string | undefined, action: string | undefined, body: Record<string, unknown>, request: Request): { status: number; body: unknown } {
  if (action && !(collection === 'follows' && action === 'promote' && method === 'POST' && id)) {
    throw new IntelError(404, 'NOT_FOUND', '生态情报入口不存在');
  }
  if (method === 'POST' && !id) {
    if (collection === 'seeds') {
      onlyKeys(body, ['x_handle', 'ecosystem', 'role_label', 'notes', 'enabled']);
      return { status: 201, body: store.insertSeed(body) };
    }
    if (collection === 'tweets') {
      onlyKeys(body, ['x_handle', 'text', 'url', 'occurred_at']);
      return { status: 201, body: store.insertTweet(body) };
    }
    onlyKeys(body, ['x_handle', 'seed_handle', 'display_name', 'bio', 'recent_summary', 'account_type', 'notes', 'occurred_at']);
    return { status: 201, body: store.insertFollow(body) };
  }
  if (!id) throw new IntelError(404, 'NOT_FOUND', '生态情报入口不存在');
  const revision = expectedRevision(request);
  if (method === 'PATCH' && collection === 'seeds' && !action) {
    onlyKeys(body, ['ecosystem', 'role_label', 'notes', 'enabled']);
    return { status: 200, body: store.updateSeed(id, revision, body) };
  }
  if (method === 'DELETE' && collection === 'seeds' && !action) {
    onlyKeys(body, []);
    store.deleteSeed(id, revision);
    return { status: 200, body: { deleted: true, seed_id: id } };
  }
  if (method === 'PATCH' && collection === 'follows' && !action) {
    onlyKeys(body, ['notes', 'account_type', 'status']);
    return { status: 200, body: store.updateFollow(id, revision, body) };
  }
  if (method === 'DELETE' && collection === 'follows' && !action) {
    onlyKeys(body, []);
    store.deleteFollow(id, revision);
    return { status: 200, body: { deleted: true, follow_id: id } };
  }
  if (method === 'POST' && collection === 'follows' && action === 'promote') {
    onlyKeys(body, ['ecosystem', 'role_label']);
    return { status: 200, body: store.promoteFollow(id, revision, body.ecosystem, body.role_label) };
  }
  throw new IntelError(405, 'VALIDATION_ERROR', '不支持的方法');
}
