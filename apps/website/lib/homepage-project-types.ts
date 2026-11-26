import {ipc, type Principal} from './projects';
import {collectProjectTypes, type ProjectTypeIndex} from './project-type-filter';

let cached: { at: number; index: ProjectTypeIndex } | null = null;
export function clearHomepageProjectTypeCache() { cached = null; }

/** Categories already stored for the homepage list. Not a tweet or paid-source lookup. */
export async function loadHomepageProjectTypes(principal: Principal, requestId: string, signal?: AbortSignal): Promise<ProjectTypeIndex> {
  if (cached && Date.now() - cached.at < 30_000) return cached.index;
  const index = await collectProjectTypes(async (membership, cursor) => {
    const query: Record<string, string> = { home_membership: membership, limit: '100', sort: 'updated', direction: 'desc' };
    if (cursor) query.cursor = cursor;
    const response = await ipc({ operation: 'list', contract: 'projects-home-v1', principal, request_id: requestId, query }, signal);
    if (!response.ok) throw Error('UPSTREAM');
    const data = (await response.json()).data;
    if (!data || !Array.isArray(data.items)) throw Error('UPSTREAM');
    return { items: data.items, next_cursor: typeof data.next_cursor === 'string' ? data.next_cursor : null };
  });
  cached = { at: Date.now(), index };
  return index;
}
