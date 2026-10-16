import { randomUUID } from "node:crypto";
import { environment } from "./config.js";
import { AuthHttp } from "./http.js";
import { AuthStore } from "./store.js";

const state=globalThis as typeof globalThis & { ikunAuth?: AuthHttp };
export function auth(): AuthHttp {
  if (!state.ikunAuth) {
    const store=new AuthStore(environment());
    // Unclassified business APIs remain admin-only until their owner declares read-only routes.
    state.ikunAuth=new AuthHttp(store,[
      /^\/api\/v1\/projects(?:\/prj_[a-f0-9-]{36})?$/,
      /^\/api\/v1\/hunter\/(?:signals|discoveries\/[^/]+)$/,
      /^\/api\/v1\/tracking\/(?:subscriptions(?:\/sub_[a-f0-9-]{36})?|latest|activities)$/,
      /^\/api\/v1\/(?:commands\/cmd_[a-f0-9-]{36}|events\/stream)$/,
    ],[/^\/$/,/^\/hunter$/, /^\/tracking$/]);
    process.once("exit",()=>{try {store.close();} catch { /* already closed */ }});
  }
  return state.ikunAuth;
}
function unavailable(request: Request) {
  const candidate=request.headers.get("x-request-id");
  const id=candidate && /^[A-Za-z0-9_-]{1,64}$/.test(candidate)?candidate:randomUUID();
  return Response.json({error:{code:"AUTH_NOT_CONFIGURED",message:"认证存储未初始化或不可用",retryable:false},request_id:id},
    {status:503,headers:{"x-request-id":id,"cache-control":"no-store"}});
}
/** Real visitor IP behind Cloudflare Tunnel (the site is only reachable through the tunnel). */
export function clientPeer(request: Request): string|undefined {
  const raw=request.headers.get("cf-connecting-ip") ?? request.headers.get("x-forwarded-for")?.split(",")[0];
  const value=raw?.trim();
  return value && /^[0-9A-Fa-f:.]{2,45}$/.test(value) ? value : undefined;
}
export async function route(request: Request) {
  try { return await auth().handle(request,clientPeer(request)); } catch { return unavailable(request); }
}
export function gate(request: Request) {
  try { return auth().gate(request); } catch { return unavailable(request); }
}
/** Safe session projection for server-side UI; never serialize the internal Identity. */
export function getSession(request:Request) {
  const http=auth();
  const actor=http.authorize(new Request(new URL('/api/v1/auth/me',http.store.cfg.origin),{headers:request.headers}),false);
  return {user_id:actor.id,username:actor.username,role:actor.role,tenant_id:actor.tenant_id,
    must_change_password:actor.must_change_password,csrf_token:actor.csrf_token};
}
export function requireIdentity(request:Request) {return auth().principal(request);}
export function requireSuperadmin(request:Request) {return auth().requireSuperadmin(request);}
/** Guard and execute in the same request handler, including automatic SSE revocation. */
export async function withAuth(request:Request,handler:Parameters<AuthHttp['business']>[1]) {
  try{return await auth().business(request,handler);}catch{return unavailable(request);}
}
