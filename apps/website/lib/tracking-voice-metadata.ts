import type { ResolveVoiceMetadata } from '@ikun/ui';

const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const revision = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;

/** Read only the existing B1-protected authoritative resources. No feed/event fallback. */
export function resolveTrackingVoiceMetadata(revoke: () => void, request: typeof fetch = fetch): ResolveVoiceMetadata {
  return async (candidate, context) => {
    async function read(path: string): Promise<Record<string, unknown> | null> {
      const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 2000);
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
      try {
        const response = await request(path, { credentials: 'same-origin', cache: 'no-store', redirect: 'error',
          signal: AbortSignal.any([context.signal, controller.signal]) });
        if (response.status === 401) { revoke(); return null; }
        if (response.status !== 200 || !response.headers.get('content-type')?.startsWith('application/json') || !response.body) return null;
        reader = response.body.getReader();
        const parts: Uint8Array[] = []; let size = 0;
        while (true) {
          const part = await reader.read(); if (part.done) break;
          size += part.value.byteLength; if (size > 32768) return null;
          parts.push(part.value);
        }
        if (context.signal.aborted || controller.signal.aborted) return null;
        const bytes = new Uint8Array(size); let offset = 0;
        for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
        const value: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
        if (!record(value) || Object.keys(value).sort().join(',') !== 'data,request_id' ||
          typeof value.request_id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(value.request_id) || !record(value.data)) return null;
        return value.data;
      } catch { return null; }
      finally { controller.abort(); clearTimeout(timer); if (reader) { await reader.cancel().catch(() => {}); reader.releaseLock(); } }
    }
    const sub = await read('/api/v1/tracking/subscriptions/' + encodeURIComponent(candidate.subscription_id));
    if (!sub || sub.subscription_id !== candidate.subscription_id || sub.project_id !== candidate.project_id ||
      !revision(sub.revision) || context.signal.aborted) return null;
    const project = await read('/api/v1/projects/' + encodeURIComponent(candidate.project_id));
    if (!project || project.project_id !== candidate.project_id || !revision(project.revision) ||
      typeof project.name !== 'string' || !project.name.trim() || project.name.length > 4000 ||
      !['S', 'A', 'B'].includes(String(project.rating)) || context.signal.aborted) return null;
    return { subscription_id: candidate.subscription_id, project_id: candidate.project_id,
      project_name: project.name, subscription_revision: sub.revision, rating: project.rating, project_revision: project.revision };
  };
}
