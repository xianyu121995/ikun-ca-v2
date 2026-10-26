import { auth } from '../../../../modules/auth/dist/src/server.js';

/** Logged-in readers may GET these paths. Writes stay superadmin-only inside authorize(). */
export const INTEL_READ_API = /^\/api\/v1\/intel\/(?:seeds|tweets|follows)(?:\/[A-Za-z0-9_-]+(?:\/promote)?)?$/;
export const INTEL_READ_PAGES = /^\/intel(?:\/tweets|\/follows)?$/;

export function isIntelRead(method: string, path: string): boolean {
  if (!['GET', 'HEAD'].includes(method)) return false;
  if (path.startsWith('/api/')) return INTEL_READ_API.test(path);
  return INTEL_READ_PAGES.test(path);
}

const state = globalThis as typeof globalThis & { ikunIntelPolicy?: boolean; ikunAuth?: object };

/** Adds eco-intel reads onto the website auth singleton. Does not change auth storage. */
export function admitIntelReads() {
  if (state.ikunIntelPolicy) return;
  const current = auth();
  const AuthHttp = current.constructor as new (
    store: typeof current.store,
    readApi: readonly RegExp[],
    readPages: readonly RegExp[],
  ) => typeof current;
  state.ikunAuth = new AuthHttp(current.store, [...current.readApi, INTEL_READ_API], [...current.readPages, INTEL_READ_PAGES]);
  state.ikunIntelPolicy = true;
}
