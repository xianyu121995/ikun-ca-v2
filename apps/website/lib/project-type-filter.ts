import {matchesProjectType,type ProjectTypeFilter} from '../features/homepage/reference-model';

/** Homepage project row, or the nested `project` object from a home-v1 list item. */
export interface ProjectTypeRecord {
  project_id?: string;
  category?: string | null;
  x_handle?: string | null;
}
export interface ProjectTypeIndex {
  byId: ReadonlyMap<string, string | null>;
  byHandle: ReadonlyMap<string, string | null>;
}
export interface RatedProject {
  project_id: string;
  state: string;
  rating: string | null;
  revision: number | null;
}

export function recordsFromListItems(items: readonly unknown[]): ProjectTypeRecord[] {
  return items.map(item => {
    if (!item || typeof item !== 'object') return {};
    const row = 'project' in item && item.project && typeof item.project === 'object' ? item.project as Record<string, unknown> : item as Record<string, unknown>;
    return {
      project_id: typeof row.project_id === 'string' ? row.project_id : undefined,
      category: typeof row.category === 'string' ? row.category : null,
      x_handle: typeof row.x_handle === 'string' ? row.x_handle : null,
    };
  });
}

export function indexProjectRecords(records: readonly ProjectTypeRecord[]): ProjectTypeIndex {
  const byId = new Map<string, string | null>();
  const byHandle = new Map<string, string | null>();
  for (const record of records) {
    if (!record.project_id) continue;
    const category = record.category ? record.category : null;
    byId.set(record.project_id, category);
    const handle = record.x_handle?.trim().replace(/^@/, '').toLowerCase();
    if (handle && !byHandle.has(handle)) byHandle.set(handle, category);
  }
  return { byId, byHandle };
}

/** Prefer the homepage project id. Fall back to the X handle when that id is absent. No match means 未分类. */
export function resolveProjectCategory(index: ProjectTypeIndex, keys: { projectId?: string | null; handle?: string | null }): string | null {
  const id = keys.projectId?.trim();
  if (id && index.byId.has(id)) return index.byId.get(id) ?? null;
  const handle = keys.handle?.trim().replace(/^@/, '').toLowerCase();
  if (handle && index.byHandle.has(handle)) return index.byHandle.get(handle) ?? null;
  return null;
}

export async function collectProjectTypes(fetchPage: (membership: 'active' | 'hidden' | 'removed', cursor: string | null) => Promise<{ items: readonly unknown[]; next_cursor?: string | null }>): Promise<ProjectTypeIndex> {
  const records: ProjectTypeRecord[] = [];
  for (const membership of ['active', 'hidden', 'removed'] as const) {
    let cursor: string | null = null;
    const seen = new Set<string>();
    for (let page = 0; page < 50; page++) {
      const data = await fetchPage(membership, cursor);
      records.push(...recordsFromListItems(data.items));
      const next = data.next_cursor ?? null;
      if (!next) break;
      if (seen.has(next) || page === 49) throw Error('UPSTREAM');
      seen.add(next);
      cursor = next;
    }
  }
  return indexProjectRecords(records);
}

/**
 * Keep every project id. Projects outside the selected type become unrated so the
 * existing S/A/B feed drops their tweets without a second category list.
 */
export function applyCategoryRatings<T extends RatedProject>(items: readonly T[], categoryOf: (projectId: string) => string | null, filter: ProjectTypeFilter | string): T[] {
  if (filter === 'all') return items.slice();
  return items.map(item => item.state === 'found' && !matchesProjectType(categoryOf(item.project_id), filter) ? { ...item, rating: null } : item);
}

export async function handlesByProjectId(readPage: (cursor: string | null) => Promise<{ items: readonly { project_id?: string; x_handle?: string | null }[]; next_cursor?: string | null }>, wanted: ReadonlySet<string>): Promise<Map<string, string>> {
  const handles = new Map<string, string>();
  if (!wanted.size) return handles;
  let cursor: string | null = null;
  const seen = new Set<string>();
  for (let page = 0; page < 20; page++) {
    const data = await readPage(cursor);
    for (const row of data.items) if (row.project_id && wanted.has(row.project_id) && row.x_handle) handles.set(row.project_id, row.x_handle);
    if ([...wanted].every(id => handles.has(id))) break;
    const next = data.next_cursor ?? null;
    if (!next || seen.has(next)) break;
    seen.add(next);
    cursor = next;
  }
  return handles;
}
