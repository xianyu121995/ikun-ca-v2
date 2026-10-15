import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { auth } from '../../../modules/auth/dist/src/server.js';

/** Invoke inside each protected Server Component, not only in a shared layout. */
export async function requireAuthPage(path: string) {
  const http=auth();
  const request=new Request(new URL(path,http.store.cfg.origin),{headers:await headers()});
  const blocked=http.gate(request);
  if(blocked) {
    const location=blocked.headers.get('location');
    if(location) redirect(location);
    throw new Error('AUTH_PAGE_DENIED');
  }
  const actor=http.authorize(request,false);
  return {username:actor.username,role:actor.role,must_change_password:actor.must_change_password,csrf_token:actor.csrf_token};
}

/** Call inside the action function immediately before executing a business write. */
export async function requireSuperadminAction(csrfToken: string) {
  const http=auth();
  return http.serverAction(new Request(new URL('/actions/business',http.store.cfg.origin),{
    method:'POST',headers:await headers(),
  }),csrfToken);
}
