import { randomUUID } from "node:crypto";
import { cookieName } from "./config.js";
import { AuthError, equal, invalid, password } from "./security.js";
import { AuthStore, publicIdentity, type Identity, type Role } from "./store.js";

const selfPaths = new Set(["/auth", "/auth/password", "/api/v1/auth/me", "/api/auth/session",
  "/api/v1/auth/logout", "/api/v1/auth/password"]);
const requestId = (request: Request) => {
  const id=request.headers.get("x-request-id");
  return id && /^[A-Za-z0-9_-]{1,64}$/.test(id) ? id : randomUUID();
};
export function tokenFrom(request: Request, name: string) {
  const entries=(request.headers.get("cookie")??"").split(";").map(value=>value.trim());
  const tokens=entries.filter(value=>value.startsWith(name+"="));
  return tokens.length===1 ? tokens[0]!.slice(name.length+1) : undefined;
}
async function body(request: Request): Promise<Record<string,unknown>> {
  const reader=request.body?.getReader();
  if (!reader) throw invalid();
  const pieces: Uint8Array[]=[]; let size=0;
  const end=Date.now()+5000;
  try {
    while (true) {
      let timer: ReturnType<typeof setTimeout> | undefined;
      const part=await Promise.race([reader.read(),new Promise<never>((_,reject)=>{
        timer=setTimeout(()=>reject(new AuthError(408,"VALIDATION_ERROR","请求超时")),Math.max(1,end-Date.now()));
      })]).finally(()=>clearTimeout(timer));
      if (part.done) break;
      size+=part.value.byteLength;
      if (size>16384) throw new AuthError(413,"VALIDATION_ERROR","请求过大");
      pieces.push(part.value);
    }
    const parsed: unknown=JSON.parse(Buffer.concat(pieces).toString("utf8"));
    if (!parsed || typeof parsed!=="object" || Array.isArray(parsed)) throw invalid();
    return parsed as Record<string,unknown>;
  } catch (error) {
    void reader.cancel().catch(()=>{});
    if (error instanceof AuthError) throw error;
    throw invalid();
  } finally { reader.releaseLock(); }
}
function fields(data: Record<string,unknown>, allowed: string[]) {
  if (Object.keys(data).some(key=>!allowed.includes(key))) throw invalid();
}
export class AuthHttp {
  readonly readApi: readonly RegExp[];
  readonly readPages: readonly RegExp[];
  constructor(readonly store: AuthStore, readApi: readonly RegExp[] = [], readPages: readonly RegExp[] = [/^\/$/]) {
    this.readApi=readApi.map(rule=>new RegExp(`^(?:${rule.source})$`,rule.flags.replace(/[gy]/g,"")));
    this.readPages=readPages.map(rule=>new RegExp(`^(?:${rule.source})$`,rule.flags.replace(/[gy]/g,"")));
  }
  private sessionData(actor: Identity) {
    return {user_id:actor.id,username:actor.username,role:actor.role,
      tenant_id:this.store.cfg.tenantId,must_change_password:actor.must_change_password,
      csrf_token:actor.csrf_token,capabilities:{can_edit_projects:actor.role==="superadmin"&&!actor.must_change_password,can_manage_hunter:actor.role==="superadmin"&&!actor.must_change_password,can_manage_tracking:actor.role==="superadmin"&&!actor.must_change_password,can_manage_users:false}};
  }
  principal(request:Request) {
    const actor=this.authorize(request);
    return Object.freeze({user_id:actor.id,tenant_id:'ikun-main' as const,role:actor.role});
  }
  requireSuperadmin(request: Request) {
    const actor=this.authorize(request);
    if(actor.role!=="superadmin" || actor.must_change_password) throw new AuthError(403,"FORBIDDEN","需要超级管理员权限");
    return Object.freeze({user_id:actor.id,tenant_id:'ikun-main' as const,role:actor.role});
  }
  serverAction(request: Request, csrfToken: string) {
    if(request.method!=="POST") throw new AuthError(405,"VALIDATION_ERROR","仅支持 POST");
    // Server Actions use multipart encoding. Verify the original Origin/Host and a form token,
    // then use the same identity/role/force-change checks as a JSON business write.
    const headers=new Headers(request.headers);
    headers.set('content-type','application/json');headers.set('x-csrf-token',csrfToken);
    return this.requireSuperadmin(new Request(new URL('/actions/business',this.store.cfg.origin),{method:'POST',headers}));
  }
  async business(request:Request,handler:(principal:{user_id:string;tenant_id:'ikun-main';role:Role})=>Response|Promise<Response>) {
    try {
      const principal=this.principal(request);
      const response=await handler(principal);
      if(response.headers.get('content-type')?.startsWith('text/event-stream')) return this.stream(request,response);
      response.headers.set('cache-control','no-store, private');response.headers.set('x-request-id',requestId(request));return response;
    } catch(error) {return this.error(request,error);}
  }
  private sessionCookie(token: string, clear=false) {
    const cfg=this.store.cfg;
    return `${cookieName(cfg)}=${token}; Path=/; Max-Age=${clear?0:cfg.absoluteTtl}; HttpOnly; SameSite=Strict${cfg.secure?"; Secure":""}`;
  }
  private response(request: Request,data: unknown,status=200,headers: Record<string,string>={}) {
    const id=requestId(request);
    return Response.json({data,request_id:id},{status,headers:{"x-request-id":id,
      "cache-control":"no-store, private","x-content-type-options":"nosniff",...headers}});
  }
  error(request: Request,error: unknown) {
    const id=requestId(request), known=error instanceof AuthError;
    const storage=error && typeof error==="object" && "code" in error && String(error.code).startsWith("ERR_SQLITE");
    const failure=known?error:storage?new AuthError(503,"DB_UNAVAILABLE","认证存储暂时不可用"):
      new AuthError(500,"INTERNAL_ERROR","认证请求未完成，请重新检查登录状态");
    return Response.json({error:{code:failure.code,message:failure.message,
      retryable:[429,503].includes(failure.status)},request_id:id},{status:failure.status,headers:{
      "cache-control":"no-store","x-request-id":id,"x-content-type-options":"nosniff",
      ...(failure.retryAfter?{"retry-after":String(failure.retryAfter)}:{})}});
  }
  private source(request: Request) {
    if (request.headers.get("host")!==new URL(this.store.cfg.origin).host)
      throw new AuthError(400,"VALIDATION_ERROR","无效的请求主机");
    for(const key of ['x-tenant','x-tenant-id','x-scope']) {
      const scope=request.headers.get(key);if(scope!==null&&scope!=='ikun-main') throw new AuthError(403,'FORBIDDEN','请求范围无权限');
    }
    const path=new URL(request.url).pathname;
    if (/\\|\/\/|%2f|%5c/i.test(path)) throw invalid("无效的请求路径");
    for (const key of ["x-http-method-override","x-http-method","x-method-override"])
      if (request.headers.has(key)) throw invalid("不允许覆盖请求方法");
  }
  private csrf(request: Request,actor?: Identity) {
    if (request.headers.get("origin")!==this.store.cfg.origin)
      throw new AuthError(403,"FORBIDDEN","请求来源验证失败");
    if (request.headers.get("content-type")?.split(";")[0]?.toLowerCase()!=="application/json")
      throw new AuthError(415,"VALIDATION_ERROR","请使用 application/json");
    if (actor && !equal(request.headers.get("x-csrf-token")??"",actor.csrf_token))
      throw new AuthError(403,"FORBIDDEN","请求验证失败，请刷新页面");
  }
  authorize(request: Request, touch=true): Identity {
    this.source(request);
    const path=new URL(request.url).pathname;
    this.noAccountManagement(path);
    const actor=this.store.authenticate(tokenFrom(request,cookieName(this.store.cfg)),
      touch && !["/api/v1/auth/me","/api/auth/session"].includes(path));
    const requestedScopes=new URL(request.url).searchParams.getAll("tenant_id");
    if (requestedScopes.some(scope=>scope!==actor.tenant_id))
      throw new AuthError(403,"FORBIDDEN","请求范围无权限");
    if (!selfPaths.has(path)) {
      if (actor.must_change_password) throw new AuthError(403,"FORBIDDEN","请先修改初始密码",0,"password-change");
      const read=["GET","HEAD"].includes(request.method) &&
        ((!path.startsWith("/api/") && !path.startsWith("/auth/") && this.readPages.some(rule=>rule.test(path))) ||
          (path.startsWith("/api/") && !path.startsWith("/api/v1/auth/") && this.readApi.some(rule=>rule.test(path))));
      if (!read && actor.role!=="superadmin")
        throw new AuthError(403,"FORBIDDEN","普通用户只能查看业务数据");
    }
    if (!["GET","HEAD","OPTIONS"].includes(request.method)) this.csrf(request,actor);
    return actor;
  }
  /** Returns a rejection Response or null. Intended for the website's Node.js proxy. */
  gate(request: Request): Response | null {
    const path=new URL(request.url).pathname;
    try {
      this.source(request);
      this.noAccountManagement(path);
      if (["/login"].includes(path) &&
          ["GET","HEAD"].includes(request.method)) return null;
      if (path==="/api/v1/auth/login" && request.method==="POST") return null;
      // The logout handler independently validates Origin and any live session/CSRF.
      if (path==="/api/v1/auth/logout" && request.method==="POST") return null;
      this.authorize(request); return null;
    } catch (error) {
      if (error instanceof AuthError && !path.startsWith("/api/") && request.method==="GET") {
        if (error.status===401) return new Response(null,{status:303,headers:{
          location:new URL("/login?next="+encodeURIComponent(path),this.store.cfg.origin).href,"cache-control":"no-store"}});
        if (error.reason==="password-change") return new Response(null,{status:303,headers:{
          location:new URL("/auth/password",this.store.cfg.origin).href,"cache-control":"no-store"}});
      }
      return this.error(request,error);
    }
  }
  private noAccountManagement(path: string) {
    // Removed endpoints stay unavailable even to superadmins, including through the proxy.
    if (path === "/auth/users" || path.startsWith("/auth/users/") ||
        path === "/api/v1/auth/users" || path.startsWith("/api/v1/auth/users/"))
      throw new AuthError(404,"NOT_FOUND","页面或接口不存在");
  }
  async handle(request: Request,peer?: string): Promise<Response> {
    const path=new URL(request.url).pathname,method=request.method;
    try {
      this.source(request);
      this.noAccountManagement(path);
      if (path==="/api/v1/auth/login" && method==="POST") {
        this.csrf(request); const data=await body(request); fields(data,["username","password"]);
        if (typeof data.username!=="string" || data.username.length>64) throw invalid();
        const result=await this.store.login(data.username,password(data.password,false),peer,
          tokenFrom(request,cookieName(this.store.cfg)));
        return this.response(request,this.sessionData(result.actor),200,
          {"set-cookie":this.sessionCookie(result.token)});
      }
      if (path==="/api/v1/auth/logout" && method==="POST") {
        this.csrf(request); fields(await body(request),[]);
        try { const actor=this.authorize(request); this.store.logout(actor); }
        catch (error) { if (!(error instanceof AuthError) || error.status!==401) throw error; }
        return this.response(request,{logged_out:true},200,{"set-cookie":this.sessionCookie("",true)});
      }
      const actor=this.authorize(request);
      if (["/api/v1/auth/me","/api/auth/session"].includes(path) && method==="GET") {
        const data={user:publicIdentity(actor),csrf_token:actor.csrf_token};
        // Narrow adapter for the separately owned tracking candidate. No other legacy auth APIs.
        return path==="/api/auth/session"?Response.json(data,{headers:{"cache-control":"no-store",
          "x-request-id":requestId(request),"x-content-type-options":"nosniff"}}):this.response(request,this.sessionData(actor));
      }
      if (path==="/api/v1/auth/password" && method==="POST") {
        const data=await body(request); fields(data,["current_password","new_password"]);
        this.store.reserveAttempt("change:"+actor.id,peer);
        const result=await this.store.changePassword(actor,password(data.current_password,false),password(data.new_password));
        return this.response(request,{changed:true,reauthentication_required:false},200,{"set-cookie":this.sessionCookie(result.token)});
      }
      throw new AuthError(404,"NOT_FOUND","认证接口不存在");
    } catch (error) { return this.error(request,error); }
  }
  /** Wrap an SSE body; revocation closes quiet streams and cancels the upstream reader. */
  stream(request: Request,upstream: Response): Response {
    let original:Identity;
    try {original=this.authorize(request,false);} catch(error) {void upstream.body?.cancel().catch(()=>{});throw error;}
    const reader=upstream.body?.getReader();
    if (!reader) return upstream;
    const store=this.store,token=tokenFrom(request,cookieName(store.cfg));
    let done=false,interval: ReturnType<typeof setInterval>;
    function valid() {
      const actor=store.authenticate(token);
      if (actor.role!==original.role || actor.must_change_password) throw deniedStream();
    }
    function deniedStream() { return new AuthError(401,"UNAUTHENTICATED","会话已撤销"); }
    const body=new ReadableStream<Uint8Array>({
      start(controller) {
        interval=setInterval(()=>{
          if (done) return;
          try { valid(); } catch {
            done=true; clearInterval(interval); controller.close(); void reader.cancel().catch(()=>{});
          }
        },1000);
        interval.unref();
      },
      async pull(controller) {
        try {
          const part=await reader.read(); if (done) return;
          valid();
          if (part.done) {done=true;clearInterval(interval);controller.close();}
          else controller.enqueue(part.value);
        } catch {
          if (!done) {done=true;clearInterval(interval);controller.close();}
          void reader.cancel().catch(()=>{});
        }
      },
      cancel() {done=true;clearInterval(interval);return reader.cancel();},
    });
    const headers=new Headers(upstream.headers);headers.set("cache-control","no-store, private");
    return new Response(body,{status:upstream.status,headers});
  }
}
