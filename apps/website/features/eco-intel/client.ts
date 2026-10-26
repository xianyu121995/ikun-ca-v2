export interface IntelFailure { message: string }

export async function readItems<T>(path: string): Promise<{ items: T[]; next_cursor: string | null }> {
  const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.error?.message || '列表不可用');
  return { items: body.data.items as T[], next_cursor: body.data.next_cursor ?? null };
}

export async function writeJson<T>(path: string, method: string, csrf: string, payload: unknown, revision?: number): Promise<T> {
  const headers: Record<string, string> = {
    'content-type': 'application/json',
    'x-csrf-token': csrf,
    'idempotency-key': crypto.randomUUID(),
  };
  if (revision) headers['if-match'] = `"rev-${revision}"`;
  const response = await fetch(path, {
    method,
    headers,
    body: JSON.stringify(payload ?? {}),
    cache: 'no-store',
    credentials: 'same-origin',
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.error?.message || '操作未确认');
  return body.data as T;
}
