import { randomUUID, createHmac } from "node:crypto";
import type { DatabaseSync } from "node:sqlite";
import type { AuthConfig } from "./config.js";
import { database } from "./database.js";
import { AuthError, equal, digest, dummyHash, hashPassword, password, secret, username, verifyPassword } from "./security.js";

export type Role = "superadmin" | "user";
interface UserRow {
  id: string; username: string; password_hash: string; role: Role; enabled: number;
  version: number; must_change_password: number; created_at: number; updated_at: number;
}
export interface Identity {
  id: string; username: string; role: Role; must_change_password: boolean;
  csrf_token: string; token_hash: string; version: number; tenant_id: string;
}
export const publicIdentity = (actor: Identity) => ({id: actor.id, username: actor.username,
  role: actor.role, must_change_password: actor.must_change_password});
const denied = () => new AuthError(401, "UNAUTHENTICATED", "请重新登录");
const forbidden = () => new AuthError(403, "FORBIDDEN", "需要超级管理员权限");
const publicUser = (row: UserRow) => ({id: row.id, username: row.username, role: row.role,
  enabled: Boolean(row.enabled), must_change_password: Boolean(row.must_change_password),
  revision: row.version, created_at: new Date(row.created_at * 1000).toISOString(),
  updated_at: new Date(row.updated_at * 1000).toISOString()});

export class AuthStore {
  readonly db: DatabaseSync;
  constructor(readonly cfg: AuthConfig, migrate = false, readonly clock = () => Date.now() / 1000) {
    this.db = database(cfg, migrate);
  }
  close() { this.db.close(); }
  now() { return Math.floor(this.clock()); }
  private tx<T>(fn: () => T): T {
    this.db.exec("BEGIN IMMEDIATE");
    try { const result = fn(); this.db.exec("COMMIT"); return result; }
    catch (error) { this.db.exec("ROLLBACK"); throw error; }
  }
  private audit(action: string, actor: string | null = null, target: string | null = null) {
    this.db.prepare("INSERT INTO auth_audit(actor_id,target_id,action,at) VALUES(?,?,?,?)")
      .run(actor, target, action, this.now());
  }
  private target(id: string): UserRow {
    const row = this.db.prepare("SELECT * FROM auth_users WHERE id=?").get(id) as unknown as UserRow | undefined;
    if (!row) throw new AuthError(404, "NOT_FOUND", "用户不存在");
    return row;
  }
  private addUser(name: string, hash: string, role: Role, change: boolean) {
    if (this.db.prepare("SELECT 1 FROM auth_users WHERE username=?").get(name))
      throw new AuthError(409, "CONFLICT", "用户名已存在");
    const id = `usr_${randomUUID()}`, now = this.now();
    this.db.prepare("INSERT INTO auth_users(id,username,password_hash,role,enabled,version,must_change_password,created_at,updated_at) VALUES(?,?,?,?,1,1,?,?,?)")
      .run(id, name, hash, role, Number(change), now, now);
    return publicUser(this.target(id));
  }
  async bootstrap(name: string, value: string) {
    name = username(name); password(value);
    if (this.db.prepare("SELECT 1 FROM auth_users WHERE role='superadmin'").get())
      throw new AuthError(409, "CONFLICT", "初始超级管理员已创建，禁止重复初始化");
    const hash = await hashPassword(value);
    return this.tx(() => {
      if (this.db.prepare("SELECT 1 FROM auth_users WHERE role='superadmin'").get())
        throw new AuthError(409, "CONFLICT", "初始超级管理员已创建，禁止重复初始化");
      const user = this.addUser(name, hash, "superadmin", false);
      this.audit("bootstrap", null, user.id); return user;
    });
  }
  reserveAttempt(key: string, peer = "website-ingress") {
    const now = this.now(), cfg = this.cfg;
    this.tx(() => {
      this.db.prepare("DELETE FROM auth_login_limits WHERE expires_at<=?").run(now);
      this.db.prepare("DELETE FROM auth_sessions WHERE expires_at<=? OR last_seen<=?").run(now, now-cfg.idleTtl);
      this.db.prepare("DELETE FROM auth_audit WHERE at<?").run(now-90*86400);
      this.db.prepare("DELETE FROM auth_idempotency WHERE expires_at<=?").run(now);
      const keys: [string,number][] = [["account:"+digest(key),cfg.accountAttempts],
        ["ip:"+digest(peer),cfg.ipAttempts], ["global",cfg.globalAttempts]];
      for (const [name, limit] of keys) {
        const row = this.db.prepare("SELECT * FROM auth_login_limits WHERE key=?").get(name);
        if (row && Number(row.attempts) >= limit)
          throw new AuthError(429,"RATE_LIMITED","登录尝试过多，请稍后重试",Number(row.expires_at)-now);
      }
      for (const [name] of keys) this.db.prepare("INSERT INTO auth_login_limits(key,attempts,expires_at) VALUES(?,1,?) " +
        "ON CONFLICT(key) DO UPDATE SET attempts=attempts+1").run(name,now+cfg.rateWindow);
    });
  }
  private newSession(user: UserRow) {
    const token=secret(), csrf=secret(), now=this.now();
    this.db.prepare("INSERT INTO auth_sessions(token_hash,user_id,csrf_token,version,created_at,last_seen,expires_at) VALUES(?,?,?,?,?,?,?)")
      .run(digest(token),user.id,csrf,user.version,now,now,now+this.cfg.absoluteTtl);
    return token;
  }
  async login(name: string, value: string, peer?: string, oldToken?: string) {
    const key=name.trim().toLowerCase();
    this.reserveAttempt(key,peer);
    const fallback=await dummyHash();
    const row=this.db.prepare("SELECT * FROM auth_users WHERE username=?").get(key) as unknown as UserRow | undefined;
    const valid=await verifyPassword(row?.password_hash ?? fallback,value);
    if (!valid || !row || !row.enabled) {
      this.audit("login_failed"); throw new AuthError(401,"UNAUTHENTICATED","用户名或密码错误");
    }
    const token=this.tx(() => {
      const current=this.target(row.id);
      if (!current.enabled || current.version !== row.version) throw denied();
      if (oldToken) this.db.prepare("DELETE FROM auth_sessions WHERE token_hash=?").run(digest(oldToken));
      this.db.prepare("DELETE FROM auth_sessions WHERE token_hash IN (SELECT token_hash FROM auth_sessions " +
        "WHERE user_id=? ORDER BY created_at DESC,rowid DESC LIMIT -1 OFFSET ?)").run(row.id,this.cfg.maxSessions-1);
      this.audit("login",row.id); return this.newSession(current);
    });
    return {token,actor:this.authenticate(token)};
  }
  private identity(tokenHash: string, admin = false): Identity {
    const row=this.db.prepare("SELECT u.*,s.token_hash,s.csrf_token,s.expires_at,s.last_seen,s.version AS session_version " +
      "FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id WHERE s.token_hash=?").get(tokenHash);
    if (!row || !["superadmin","user"].includes(String(row.role)) || !row.enabled || row.version !== row.session_version || Number(row.expires_at)<=this.now() ||
        Number(row.last_seen)+this.cfg.idleTtl<=this.now()) throw denied();
    if (admin && (row.role !== "superadmin" || row.must_change_password)) throw forbidden();
    return {id:String(row.id),username:String(row.username),role:row.role as Role,
      must_change_password:Boolean(row.must_change_password),csrf_token:String(row.csrf_token),
      token_hash:tokenHash,version:Number(row.version),tenant_id:this.cfg.tenantId};
  }
  authenticate(token: string | undefined, touch=false): Identity {
    if (!token || token.length>128) throw denied();
    if (!touch) return this.identity(digest(token));
    return this.tx(() => {
      const actor=this.identity(digest(token));
      this.db.prepare("UPDATE auth_sessions SET last_seen=? WHERE token_hash=?").run(this.now(),actor.token_hash);
      return actor;
    });
  }
  logout(actor: Identity) {
    this.tx(() => {
      this.identity(actor.token_hash);
      this.db.prepare("DELETE FROM auth_sessions WHERE token_hash=?").run(actor.token_hash);
      this.audit("logout",actor.id);
    });
  }
  users(actor: Identity) {
    this.identity(actor.token_hash,true);
    return (this.db.prepare("SELECT * FROM auth_users ORDER BY created_at,id").all() as unknown as UserRow[]).map(publicUser);
  }
  pageUsers(actor:Identity,limit=50,cursor?:string) {
    this.identity(actor.token_hash,true);
    if(!Number.isSafeInteger(limit)||limit<1||limit>100) throw new AuthError(422,'VALIDATION_ERROR','limit须为1–100');
    const key=String(this.db.prepare("SELECT value FROM auth_metadata WHERE key='cursor_key'").get()?.value);
    let after:{at:number;id:string}|undefined;
    if(cursor) {
      try {
        if(cursor.length>1024) throw new Error();
        const [encoded,signature,...extra]=cursor.split('.');
        if(!encoded||!signature||extra.length||!equal(createHmac('sha256',key).update(encoded).digest('base64url'),signature)) throw new Error();
        const value=JSON.parse(Buffer.from(encoded,'base64url').toString());
        if(value.scope!==this.cfg.tenantId||value.actor!==actor.id||value.query!=='auth-users-v1'||value.limit!==limit||
           !Number.isSafeInteger(value.at)||typeof value.id!=='string') throw new Error();
        after={at:value.at,id:value.id};
      } catch {throw new AuthError(422,'VALIDATION_ERROR','cursor无效或不属于当前查询');}
    }
    const rows=(after?this.db.prepare('SELECT * FROM auth_users WHERE (created_at,id)>(?,?) ORDER BY created_at,id LIMIT ?')
      .all(after.at,after.id,limit+1):this.db.prepare('SELECT * FROM auth_users ORDER BY created_at,id LIMIT ?').all(limit+1)) as unknown as UserRow[];
    const items=rows.slice(0,limit).map(row=>{const {id,...rest}=publicUser(row);return {user_id:id,...rest};});
    const last=rows[limit-1];let next_cursor:string|null=null;
    if(rows.length>limit&&last) {
      const payload=Buffer.from(JSON.stringify({scope:this.cfg.tenantId,actor:actor.id,query:'auth-users-v1',limit,at:last.created_at,id:last.id})).toString('base64url');
      next_cursor=payload+'.'+createHmac('sha256',key).update(payload).digest('base64url');
    }
    return {items,next_cursor};
  }
  private prior(actor: Identity,route: string,key: string) {
    this.identity(actor.token_hash,true);
    return this.db.prepare("SELECT * FROM auth_idempotency WHERE actor_id=? AND route=? AND key=? AND expires_at>?")
      .get(actor.id,route,key,this.now());
  }
  private async replay(actor: Identity,route: string,key: string,body: string) {
    const row=this.prior(actor,route,key);
    if (!row) return undefined;
    if (!await verifyPassword(String(row.body_hash),body))
      throw new AuthError(409,"IDEMPOTENCY_CONFLICT","同一幂等键不能用于不同请求");
    this.identity(actor.token_hash,true);
    return JSON.parse(String(row.response)) as Record<string,unknown>;
  }
  private remember(actor: Identity,route: string,key: string,hash: string,result: unknown) {
    this.db.prepare("INSERT INTO auth_idempotency(actor_id,route,key,body_hash,response,expires_at) VALUES(?,?,?,?,?,?)")
      .run(actor.id,route,key,hash,JSON.stringify(result),this.now()+7*86400);
  }
  async createUser(actor: Identity,name: string,value: string,role: Role,key: string) {
    name=username(name); password(value);
    if (role!=="superadmin" && role!=="user") throw new AuthError(422,"VALIDATION_ERROR","角色无效");
    const route="create",body=JSON.stringify([name,value,role]);
    const replay=await this.replay(actor,route,key,body); if (replay) return replay;
    const hash=await hashPassword(value),bodyHash=await hashPassword(body);
    return this.tx(() => {
      this.identity(actor.token_hash,true);
      if (this.prior(actor,route,key)) throw new AuthError(409,"CONFLICT","请求处理中，请使用相同幂等键重试");
      const user=this.addUser(name,hash,role,true);
      this.audit("user_created",actor.id,user.id); this.remember(actor,route,key,bodyHash,user); return user;
    });
  }
  async setEnabled(actor:Identity,id:string,enabled:boolean,revision:number,key:string) {
    return this.patchUser(actor,id,{enabled},revision,key);
  }
  async patchUser(actor:Identity,id:string,patch:{enabled?:boolean;role?:Role;must_change_password?:boolean},revision:number,key:string) {
    const keys=Object.keys(patch).sort();
    if(!keys.length||keys.some(k=>!['enabled','role','must_change_password'].includes(k))||
       ('enabled' in patch&&typeof patch.enabled!=='boolean')||
       ('must_change_password' in patch&&typeof patch.must_change_password!=='boolean')||
       ('role' in patch&&patch.role!=='superadmin'&&patch.role!=='user'))
      throw new AuthError(422,'VALIDATION_ERROR','用户修改字段无效');
    const route=`patch:${id}`,body=JSON.stringify([Object.fromEntries(keys.map(k=>[k,patch[k as keyof typeof patch]])),revision]);
    const replay=await this.replay(actor,route,key,body);if(replay) return replay;
    const bodyHash=await hashPassword(body);
    return this.tx(()=>{
      this.identity(actor.token_hash,true);
      if(this.prior(actor,route,key)) throw new AuthError(409,'CONFLICT','请求处理中，请重试');
      const user=this.target(id);
      if(user.version!==revision) throw new AuthError(409,'VERSION_CONFLICT','用户资料已更新，请刷新');
      const enabled=patch.enabled??Boolean(user.enabled),role=patch.role??user.role;
      const change=patch.must_change_password??Boolean(user.must_change_password);
      if(user.enabled&&user.role==='superadmin'&&(!enabled||role!=='superadmin')&&
         Number(this.db.prepare("SELECT count(*) AS n FROM auth_users WHERE enabled=1 AND role='superadmin'").get()?.n)<=1)
        throw new AuthError(409,'CONFLICT','不能禁用或降级最后一个可用超级管理员');
      if(enabled!==Boolean(user.enabled)||role!==user.role||change!==Boolean(user.must_change_password)) {
        this.db.prepare('UPDATE auth_users SET enabled=?,role=?,must_change_password=?,version=version+1,updated_at=? WHERE id=?')
          .run(Number(enabled),role,Number(change),this.now(),id);
        this.db.prepare('DELETE FROM auth_sessions WHERE user_id=?').run(id);
        this.audit('user_updated',actor.id,id);
      }
      const result=publicUser(this.target(id));this.remember(actor,route,key,bodyHash,result);return result;
    });
  }
  async resetPassword(actor: Identity,id: string,value: string,revision: number,key: string) {
    password(value);
    const route=`reset:${id}`,body=JSON.stringify([value,revision]);
    const replay=await this.replay(actor,route,key,body); if (replay) return replay;
    const user=this.target(id);
    if (await verifyPassword(user.password_hash,value)) throw new AuthError(422,"VALIDATION_ERROR","新密码不能与当前密码相同");
    const hash=await hashPassword(value),bodyHash=await hashPassword(body);
    return this.tx(() => {
      this.identity(actor.token_hash,true);
      if (this.prior(actor,route,key)) throw new AuthError(409,"CONFLICT","请求处理中，请重试");
      if (this.target(id).version!==revision) throw new AuthError(409,"VERSION_CONFLICT","用户资料已更新，请刷新");
      this.db.prepare("UPDATE auth_users SET password_hash=?,version=version+1,must_change_password=1,updated_at=? WHERE id=?")
        .run(hash,this.now(),id);
      this.db.prepare("DELETE FROM auth_sessions WHERE user_id=?").run(id);
      this.audit("password_reset",actor.id,id);
      const result=publicUser(this.target(id)); this.remember(actor,route,key,bodyHash,result); return result;
    });
  }
  async changePassword(actor: Identity,current: string,value: string) {
    password(value); this.identity(actor.token_hash);
    const before=this.target(actor.id);
    if (!await verifyPassword(before.password_hash,current)) throw new AuthError(422,"VALIDATION_ERROR","当前密码错误");
    if (await verifyPassword(before.password_hash,value)) throw new AuthError(422,"VALIDATION_ERROR","新密码不能与当前密码相同");
    const hash=await hashPassword(value);
    this.tx(() => {
      this.identity(actor.token_hash);
      if (this.target(actor.id).version!==before.version) throw denied();
      this.db.prepare("UPDATE auth_users SET password_hash=?,version=version+1,must_change_password=0,updated_at=? WHERE id=?")
        .run(hash,this.now(),actor.id);
      this.db.prepare("DELETE FROM auth_sessions WHERE user_id=?").run(actor.id);
      this.audit("password_changed",actor.id,actor.id);
    });
    return {changed:true as const,reauthentication_required:true as const};
  }
}
