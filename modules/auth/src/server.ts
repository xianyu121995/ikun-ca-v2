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
export async function route(request: Request) {
  try { return await auth().handle(request); } catch { return unavailable(request); }
}
export function page(request: Request) {
  try { return auth().page(request); } catch { return unavailable(request); }
}
export function gate(request: Request) {
  try { return auth().gate(request); } catch { return unavailable(request); }
}
