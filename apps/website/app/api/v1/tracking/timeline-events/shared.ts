/** BFF for tracking-owned AI timeline entries. Projects milestones are not written here. */
import {projectsAuth, ipc, requestId, failure, type Principal} from '../../../../../lib/projects';
import {trackingService, readBody} from '../../../../../lib/tracking';
import {requireIdentity, requireSuperadmin, withAuth} from '../../../../../../../modules/auth/dist/src/server.js';

const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const entryId = /^tle_[0-9a-f]{32}$/;
const projectId = new RegExp('^prj_' + uuid + '$');
const date = /^\d{4}-\d{2}-\d{2}$/;
const hour = /^(?:[01]\d|2[0-3])$/;
const tweet = /^[0-9]{1,40}$/;
const url = /^https:\/\/x\.com\/[A-Za-z0-9_]{1,15}\/status\/[0-9]{1,40}$/;
const types = new Set(['tge', 'mint', 'airdrop', 'listing', 'whitelist', 'launch', 'mainnet', 'snapshot', 'other']);
const grades = ['S', 'A', 'B', 'C', 'D'] as const;

export type TimelineEntry = {
  entry_id: string;
  project_id: string;
  project_name: string;
  rating: (typeof grades)[number] | null;
  event_type: string;
  title: string;
  starts_at: string;
  date: string;
  hour: string | null;
  status: 'confirmed' | 'estimated';
  confidence: number;
  source_tweet_id: string;
  source_url: string | null;
};

function asEntry(value: unknown): Omit<TimelineEntry, 'rating'> | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as Record<string, unknown>;
  const idValue = typeof row.entry_id === 'string' ? row.entry_id : '';
  const project = typeof row.project_id === 'string' ? row.project_id : '';
  if (!entryId.test(idValue) || !projectId.test(project)) return null;
  if (typeof row.event_type !== 'string' || !types.has(row.event_type)) return null;
  if (typeof row.title !== 'string' || !row.title.trim() || row.title.length > 60) return null;
  if (typeof row.date !== 'string' || !date.test(row.date) || Number.isNaN(Date.parse(row.date + 'T00:00:00Z'))) return null;
  if (row.hour !== null && (typeof row.hour !== 'string' || !hour.test(row.hour))) return null;
  if (row.status !== 'confirmed' && row.status !== 'estimated') return null;
  if (typeof row.starts_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(row.starts_at)) return null;
  if (typeof row.source_tweet_id !== 'string' || !tweet.test(row.source_tweet_id)) return null;
  if (row.source_url !== null && (typeof row.source_url !== 'string' || !url.test(row.source_url))) return null;
  if (typeof row.confidence !== 'number' || !Number.isFinite(row.confidence)) return null;
  const name = typeof row.project_name === 'string' ? row.project_name.slice(0, 120) : '';
  const clock = row.hour === null ? null : row.hour;
  const link = row.source_url === null ? null : row.source_url;
  if ((clock !== null && typeof clock !== 'string') || (link !== null && typeof link !== 'string')) return null;
  return {
    entry_id: idValue, project_id: project, project_name: name, event_type: row.event_type,
    title: row.title, starts_at: row.starts_at, date: row.date, hour: clock, status: row.status,
    confidence: row.confidence, source_tweet_id: row.source_tweet_id, source_url: link,
  };
}

async function ratingsFor(ids: string[], principal: Principal, requestIdValue: string, signal: AbortSignal) {
  const map = new Map<string, TimelineEntry['rating']>();
  if (!ids.length) return map;
  try {
    const response = await ipc({operation: 'ratings', contract: 'tracking-ratings-v1', principal, request_id: requestIdValue, body: {project_ids: ids.slice(0, 200), expected_catalog_version: null}}, signal);
    if (!response.ok) return map;
    const body = await response.json() as {data?: {items?: {project_id?: string; rating?: unknown}[]}};
    for (const item of body.data?.items ?? []) {
      if (item && typeof item.project_id === 'string' && grades.includes(item.rating as typeof grades[number])) map.set(item.project_id, item.rating as TimelineEntry['rating']);
    }
  } catch { /* A missing grade still leaves the entry on the timeline. */ }
  return map;
}

export function listTimeline(request: Request) {
  projectsAuth();
  return withAuth(request, async () => {
    const principal = requireIdentity(request);
    const id = requestId(request);
    const upstream = await trackingService('timeline-events', id, {signal: request.signal});
    if (!upstream.ok) return new Response(upstream.body, {status: upstream.status, headers: {'content-type': upstream.headers.get('content-type') ?? 'application/json', 'cache-control': 'no-store', 'x-request-id': id}});
    const body = await upstream.json() as {data?: {items?: unknown[]}};
    const rows = (Array.isArray(body.data?.items) ? body.data.items : []).map(asEntry).filter((row): row is Omit<TimelineEntry, 'rating'> => !!row);
    const gradesByProject = await ratingsFor([...new Set(rows.map(row => row.project_id))], principal, id, request.signal);
    const items = rows.map(row => ({...row, rating: gradesByProject.get(row.project_id) ?? null}));
    return Response.json({data: {items}, request_id: id}, {headers: {'cache-control': 'no-store'}});
  });
}

function patchOf(body: Record<string, unknown>) {
  if (Object.keys(body).some(key => !['date', 'hour', 'title', 'status'].includes(key))) return null;
  if (typeof body.date !== 'string' || !date.test(body.date)) return null;
  if (body.hour !== null && (typeof body.hour !== 'string' || !hour.test(body.hour))) return null;
  if (typeof body.title !== 'string' || !body.title.trim() || body.title.trim().length > 60) return null;
  if (body.status !== 'confirmed' && body.status !== 'estimated') return null;
  return {date: body.date, hour: body.hour, title: body.title.trim(), status: body.status};
}

export function mutateTimeline(request: Request, entry: string, method: 'PATCH' | 'DELETE') {
  projectsAuth();
  return withAuth(request, async () => {
    const principal = requireSuperadmin(request);
    const id = requestId(request);
    if (!entryId.test(entry)) return failure(id, 422, 'VALIDATION_ERROR', '时间线条目 ID 不正确');
    const key = request.headers.get('idempotency-key');
    if (!key || !new RegExp('^' + uuid + '$').test(key)) return failure(id, 422, 'VALIDATION_ERROR', '需要 UUID Idempotency-Key');
    let body: Record<string, unknown>;
    try { body = await readBody(request, method === 'DELETE'); } catch { return failure(id, 422, 'VALIDATION_ERROR', '无效 JSON'); }
    const patch = method === 'PATCH' ? patchOf(body) : null;
    if (method === 'PATCH' && !patch) return failure(id, 422, 'VALIDATION_ERROR', '时间线条目字段不正确');
    if (method === 'DELETE' && Object.keys(body).length) return failure(id, 422, 'VALIDATION_ERROR', '删除不接受字段');
    const upstream = await trackingService('timeline-events/' + entry, id, {
      method,
      headers: {'idempotency-key': key},
      body: JSON.stringify(method === 'DELETE' ? {actor: principal} : {actor: principal, patch}),
      signal: request.signal,
    });
    return new Response(upstream.body, {status: upstream.status, headers: {'content-type': upstream.headers.get('content-type') ?? 'application/json', 'cache-control': 'no-store', 'x-request-id': id}});
  });
}
