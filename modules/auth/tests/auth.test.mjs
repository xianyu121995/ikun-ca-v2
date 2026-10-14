import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtempSync, mkdirSync, rmSync, readFileSync, symlinkSync, linkSync, statSync } from "node:fs";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";
import { setTimeout as delay } from "node:timers/promises";
import { spawnSync } from "node:child_process";
import { config,cookieName } from "../dist/src/config.js";
import { APP_ID } from "../dist/src/database.js";
import { AuthHttp } from "../dist/src/http.js";
import { AuthStore } from "../dist/src/store.js";
import { verifyPassword } from "../dist/src/security.js";

const password="unit-test-initial-long-passphrase",changed="unit-test-changed-long-passphrase";
const origin="http://127.0.0.1:3600";
async function fixture(run,overrides={}) {
  const directory=mkdtempSync("/private/tmp/ikun-auth-node-");
  let now=1800000000;
  const cfg=config({dataRoot:directory,origin,secure:false,...overrides});
  let store=new AuthStore(cfg,true,()=>now);
  const admin=await store.bootstrap("root_admin",password);
  let api=new AuthHttp(store,[/^\/api\/v1\/projects(?:\/[^/]+)?$/],[/^\/$/,/^\/projects$/]);
  const env={cfg,directory,admin,get store(){return store;},get api(){return api;},
    advance(value){now+=value;},restart(){store.close();store=new AuthStore(cfg,false,()=>now);
      api=new AuthHttp(store,[/^\/api\/v1\/projects(?:\/[^/]+)?$/],[/^\/$/,/^\/projects$/]);}};
  try {await run(env);} finally {store.close();rmSync(directory,{recursive:true,force:true});}
}
function request(path,method="GET",data,session,extra={}) {
  const headers={host:new URL(origin).host,...extra};
  if (session) {headers.cookie=session.cookie;headers["x-csrf-token"]=session.csrf;}
  if (data!==undefined) {headers["content-type"]="application/json";headers.origin=origin;}
  return new Request(origin+path,{method,headers,...(data!==undefined?{body:JSON.stringify(data)}:{})});
}
async function login(env,name="root_admin",value=password,previous) {
  const response=await env.api.handle(request("/api/v1/auth/login","POST",{username:name,password:value},previous));
  assert.equal(response.status,200,await response.clone().text());
  const body=await response.json();
  return {cookie:response.headers.get("set-cookie").split(";")[0],csrf:body.data.csrf_token,data:body.data};
}
const token=session=>session.cookie.split("=")[1];
const actor=(env,session)=>env.store.authenticate(token(session));
const mutation=(revision,key=randomUUID())=>({"if-match":`"rev-${revision}"`,"idempotency-key":key});
async function viewer(env) {
  const root=await login(env);
  const user=await env.store.createUser(actor(env,root),"viewer",password,"user",randomUUID());
  const first=await login(env,"viewer");
  const response=await env.api.handle(request("/api/v1/auth/password","POST",{
    current_password:password,new_password:changed},first));
  assert.equal(response.status,200,await response.clone().text());
  const body=await response.json();
  return {root,user,session:{cookie:response.headers.get("set-cookie").split(";")[0],csrf:body.data.csrf_token,data:body.data}};
}

for (const path of ["/","/projects","/api/v1/projects","/api/v1/auth/me","/auth/users"])
  test(`anonymous denied: ${path}`,()=>fixture(async env=>{
    const blocked=env.api.gate(request(path));
    assert.ok(blocked);assert.equal(blocked.status,path.startsWith("/api/")?401:303);
    if (!path.startsWith("/api/")) assert.ok(blocked.headers.get("location").startsWith(origin+"/login?next="));
  }));

test("public login/assets only; registration unavailable",()=>fixture(async env=>{
  assert.equal(env.api.page(request("/login")).status,200);
  assert.equal(env.api.page(request("/auth/assets/auth.css")).status,200);
  assert.equal((await env.api.handle(request("/api/v1/auth/register","POST",{}))).status,401);
  assert.ok(env.api.gate(request("/auth/assets/users.html")));
}));

for (const method of ["POST","PUT","PATCH","DELETE"])
  test(`ordinary user cannot write business data: ${method}`,()=>fixture(async env=>{
    const {session}=await viewer(env);
    const blocked=env.api.gate(request("/api/v1/projects/1",method,{},session));
    assert.equal(blocked.status,403);
  }));

test("reader views audited GET; unknown GET, Hunter configuration and user admin denied",()=>fixture(async env=>{
  const {session}=await viewer(env);
  assert.equal(env.api.gate(request("/projects","GET",undefined,session)),null);
  assert.equal(env.api.gate(request("/api/v1/projects","GET",undefined,session)),null);
  for (const path of ["/api/v1/sync-on-get","/api/v1/hunter/accounts","/auth/users","/api/v1/auth/users"])
    assert.equal(env.api.gate(request(path,"GET",undefined,session)).status,403);
  for (const [path,body] of [["/api/v1/auth/users",{username:"escalate",password,role:"superadmin"}],
    ["/api/v1/monitors/start",{}]])
    assert.equal(env.api.gate(request(path,"POST",body,session)).status,403);
}));

test("superadmin business writes authorized; CSRF and Origin remain mandatory",()=>fixture(async env=>{
  const session=await login(env);
  for (const method of ["POST","PUT","PATCH","DELETE"])
    assert.equal(env.api.gate(request("/api/v1/projects/1",method,{},session)),null);
  const noCsrf=request("/api/v1/monitors/start","POST",{},session);noCsrf.headers.delete("x-csrf-token");
  assert.equal(env.api.gate(noCsrf).status,403);
  const cross=request("/api/v1/monitors/start","POST",{},session);cross.headers.set("origin","https://evil.example");
  assert.equal(env.api.gate(cross).status,403);
  const form=request("/api/v1/auth/login","POST",{});form.headers.set("content-type","application/x-www-form-urlencoded");
  assert.equal((await env.api.handle(form)).status,415);
  const absent=request("/api/v1/auth/login","POST",{});absent.headers.delete("origin");
  assert.equal((await env.api.handle(absent)).status,403);
}));

test("new/reset users must change password before any business access",()=>fixture(async env=>{
  const root=await login(env);
  await env.store.createUser(actor(env,root),"viewer",password,"user",randomUUID());
  const session=await login(env,"viewer");
  assert.ok(session.data.must_change_password);
  assert.equal(env.api.gate(request("/api/v1/projects","GET",undefined,session)).status,403);
  const redirect=env.api.gate(request("/projects","GET",undefined,session));
  assert.equal(redirect.status,303);assert.equal(redirect.headers.get("location"),origin+"/auth/password");
  assert.equal(env.api.gate(request("/api/v1/auth/me","GET",undefined,session)),null);
}));

test("create, disable, enable, reset, version checks and all-device revocation",()=>fixture(async env=>{
  const {root,user,session}=await viewer(env);
  let response=await env.api.handle(request(`/api/v1/auth/users/${user.id}`,"PATCH",{enabled:false},root,mutation(1)));
  assert.equal(response.status,409); // First password change advanced revision to 2.
  response=await env.api.handle(request(`/api/v1/auth/users/${user.id}`,"PATCH",{enabled:false},root,mutation(2)));
  assert.equal(response.status,200);
  assert.throws(()=>actor(env,session),error=>error.status===401);
  response=await env.api.handle(request("/api/v1/auth/login","POST",{username:"viewer",password:changed}));
  assert.equal(response.status,401);
  assert.equal((await response.json()).error.message,"用户名或密码错误");
  response=await env.api.handle(request(`/api/v1/auth/users/${user.id}`,"PATCH",{enabled:true},root,mutation(3)));
  assert.equal(response.status,200);
  const logged=await login(env,"viewer",changed);
  response=await env.api.handle(request(`/api/v1/auth/users/${user.id}/reset-password`,"POST",{password},root,mutation(4)));
  assert.equal(response.status,200);
  assert.throws(()=>actor(env,logged),error=>error.status===401);
  const reset=await login(env,"viewer");assert.ok(reset.data.must_change_password);
}));

test("account writes require Idempotency-Key/If-Match and forbid extra fields/third role",()=>fixture(async env=>{
  const root=await login(env);
  for (const role of ["admin","viewer","editor"])
    assert.equal((await env.api.handle(request("/api/v1/auth/users","POST",{username:"bad",password,role},root,mutation(1)))).status,422);
  assert.equal((await env.api.handle(request("/api/v1/auth/users","POST",{username:"viewer",password},root))).status,422);
  assert.equal((await env.api.handle(request(`/api/v1/auth/users/${env.admin.id}`,"PATCH",{enabled:false},root,
    {"idempotency-key":randomUUID()}))).status,428);
  const extra=await env.api.handle(request("/api/v1/auth/users","POST",{username:"viewer",password,tenant_id:"other"},root,mutation(1)));
  assert.equal(extra.status,422);
}));

test("idempotency persists across restart and rejects conflicting payload",()=>fixture(async env=>{
  const root=await login(env),key=randomUUID(),body={username:"viewer",password,role:"user"};
  let response=await env.api.handle(request("/api/v1/auth/users","POST",body,root,{"idempotency-key":key}));
  assert.equal(response.status,201);const first=(await response.json()).data;
  env.restart();
  response=await env.api.handle(request("/api/v1/auth/users","POST",body,root,{"idempotency-key":key}));
  assert.equal(response.status,201);assert.deepEqual((await response.json()).data,first);
  response=await env.api.handle(request("/api/v1/auth/users","POST",{...body,password:changed},root,{"idempotency-key":key}));
  assert.equal(response.status,409);
  const persisted=JSON.stringify(env.store.db.prepare("SELECT * FROM auth_idempotency").all());
  assert.ok(!persisted.includes(password));assert.ok(persisted.includes("argon2id"));
}));

test("last enabled admin is protected, including simultaneous attempts",()=>fixture(async env=>{
  const root=await login(env),first=actor(env,root);
  await assert.rejects(env.store.setEnabled(first,first.id,false,1,randomUUID()),error=>error.status===409);
  const other=await env.store.createUser(first,"second_admin",password,"superadmin",randomUUID());
  const initial=await env.store.login("second_admin",password,"loopback");
  const next=await env.store.changePassword(initial.actor,password,changed);
  const results=await Promise.allSettled([
    env.store.setEnabled(first,other.id,false,2,randomUUID()),
    env.store.setEnabled(next.actor,first.id,false,1,randomUUID())]);
  assert.equal(results.filter(item=>item.status==="fulfilled").length,1);
  assert.equal(env.store.db.prepare("SELECT count(*) AS n FROM auth_users WHERE enabled=1 AND role='superadmin'").get().n,1);
}));

test("stale admin identity is rechecked inside write transaction",()=>fixture(async env=>{
  const root=await login(env),who=actor(env,root);
  const work=env.store.createUser(who,"new_user",password,"user",randomUUID());
  env.store.db.prepare("UPDATE auth_users SET enabled=0 WHERE id=?").run(who.id);
  await assert.rejects(work,error=>error.status===401);
  assert.equal(env.store.db.prepare("SELECT count(*) AS n FROM auth_users").get().n,1);
}));

test("session rotation, persistent sessions, logout and idempotent logout",()=>fixture(async env=>{
  const first=await login(env),second=await login(env,"root_admin",password,first);
  assert.notEqual(first.cookie,second.cookie);assert.notEqual(first.csrf,second.csrf);
  assert.throws(()=>actor(env,first),error=>error.status===401);
  env.restart();assert.equal(actor(env,second).role,"superadmin");
  const response=await env.api.handle(request("/api/v1/auth/logout","POST",{},second));
  assert.equal(response.status,200);assert.ok(response.headers.get("set-cookie").includes("Max-Age=0"));
  assert.throws(()=>actor(env,second),error=>error.status===401);
  assert.equal((await env.api.handle(request("/api/v1/auth/logout","POST",{},second))).status,200);
}));

test("self password change rotates current session and invalidates other devices",()=>fixture(async env=>{
  const first=await login(env),second=await login(env);
  const response=await env.api.handle(request("/api/v1/auth/password","POST",{
    current_password:password,new_password:changed},first));
  assert.equal(response.status,200);
  assert.throws(()=>actor(env,first),error=>error.status===401);
  assert.throws(()=>actor(env,second),error=>error.status===401);
  const next=await login(env,"root_admin",changed);assert.equal(next.data.must_change_password,false);
}));

test("idle expiry is not extended by background me polling",()=>fixture(async env=>{
  const root=await login(env);
  env.advance(1000);assert.equal((await env.api.handle(request("/api/v1/auth/me","GET",undefined,root))).status,200);
  env.advance(800);assert.equal((await env.api.handle(request("/api/v1/auth/me","GET",undefined,root))).status,401);
}));
test("absolute expiry survives ongoing activity",()=>fixture(async env=>{
  const root=await login(env);
  for (let i=0;i<4;i++) {env.advance(100);assert.equal(env.api.gate(request("/projects","GET",undefined,root)),null);}
  env.advance(100);assert.equal(env.api.gate(request("/projects","GET",undefined,root)).status,303);
},{absoluteTtl:500}));

test("login limits persist and ignore forged forwarding identity",()=>fixture(async env=>{
  for (let i=0;i<3;i++) assert.equal((await env.api.handle(request("/api/v1/auth/login","POST",{
    username:"ghost",password:"wrong"},undefined,{"x-forwarded-for":`192.0.2.${i}`}))).status,401);
  env.restart();
  const response=await env.api.handle(request("/api/v1/auth/login","POST",{username:"ghost",password:"wrong"}));
  assert.equal(response.status,429);assert.ok(Number(response.headers.get("retry-after"))>0);
  env.advance(900);
  assert.equal((await env.api.handle(request("/api/v1/auth/login","POST",{username:"ghost",password:"wrong"}))).status,401);
},{accountAttempts:3}));

test("Argon2id hashes, hashed tokens, private permissions, no response secrets",()=>fixture(async env=>{
  const root=await login(env);
  const user=env.store.db.prepare("SELECT * FROM auth_users").get();
  assert.ok(user.password_hash.startsWith("$argon2id$v=19$m=65536,t=3,p=1$"));
  assert.ok(await verifyPassword(user.password_hash,password));
  const session=env.store.db.prepare("SELECT * FROM auth_sessions").get();
  assert.notEqual(session.token_hash,token(root));assert.equal(session.token_hash.length,64);
  assert.equal(statSync(join(env.directory,"auth/auth.db")).mode&0o777,0o600);
  const response=await env.api.handle(request("/api/v1/auth/login","POST",{username:"root_admin",password:[password]}));
  assert.equal(response.status,422);assert.ok(!(await response.text()).includes(password));
  const audit=JSON.stringify(env.store.db.prepare("SELECT * FROM auth_audit").all());
  assert.ok(!audit.includes(password)&&!audit.includes(token(root)));
}));

test("body bound, host/method spoofing, duplicate cookies, JSON envelope",()=>fixture(async env=>{
  const large=request("/api/v1/auth/login","POST",{password:"x".repeat(20000)});
  const response=await env.api.handle(large);assert.equal(response.status,413);
  const json=await response.json();assert.ok(json.request_id);assert.equal(json.error.retryable,false);
  assert.equal(env.api.gate(request("/projects","GET",undefined,undefined,{"x-user":"root_admin","x-role":"superadmin"})).status,303);
  assert.equal(env.api.gate(request("/login","GET",undefined,undefined,{host:"evil.example"})).status,400);
  const root=await login(env);
  assert.equal(env.api.gate(request("/api/v1/projects","GET",undefined,root,{"x-http-method-override":"DELETE"})).status,422);
  const duplicate=request("/api/v1/auth/me","GET",undefined,root);duplicate.headers.append("cookie",root.cookie);
  assert.equal((await env.api.handle(duplicate)).status,401);
}));

test("secure cookie production flags and CSP",async()=>{
  const directory=mkdtempSync("/private/tmp/ikun-auth-secure-");
  const cfg=config({dataRoot:directory,origin:"https://ikun.ca",secure:true});
  const store=new AuthStore(cfg,true),api=new AuthHttp(store);
  try {
    await store.bootstrap("root_admin",password);
    const page=api.page(new Request("https://ikun.ca/login",{headers:{host:"ikun.ca"}}));
    assert.ok(page.headers.get("content-security-policy").includes("frame-ancestors 'none'"));
    const response=await api.handle(new Request("https://ikun.ca/api/v1/auth/login",{method:"POST",headers:{
      host:"ikun.ca",origin:"https://ikun.ca","content-type":"application/json"},body:JSON.stringify({username:"root_admin",password})}));
    assert.equal(response.status,200);
    const cookie=response.headers.get("set-cookie");
    for (const flag of ["__Host-ikun_session=","Secure","HttpOnly","SameSite=Strict","Path=/"]) assert.ok(cookie.includes(flag));
    assert.ok(!cookie.includes("Domain="));
  } finally {store.close();rmSync(directory,{recursive:true,force:true});}
});

test("no default account; bootstrap once; CLI rejects piped passwords",async()=>{
  const directory=mkdtempSync("/private/tmp/ikun-auth-blank-");
  const cfg=config({dataRoot:directory,origin,secure:false});const store=new AuthStore(cfg,true);
  try {
    assert.equal(store.db.prepare("SELECT count(*) AS n FROM auth_users").get().n,0);
    await store.bootstrap("root_admin",password);
    await assert.rejects(store.bootstrap("other",password),error=>error.status===409);
    const command=spawnSync(process.execPath,[new URL("../dist/src/cli.js",import.meta.url).pathname,"bootstrap","--username","root"],{
      input:password,encoding:"utf8",env:{...process.env,DATA_ROOT:directory}});
    assert.equal(command.status,1);assert.ok(!(command.stdout+command.stderr).includes(password));
  } finally {store.close();rmSync(directory,{recursive:true,force:true});}
});

test("physical DB isolation, foreign DB and file aliases rejected",async()=>{
  const directory=mkdtempSync("/private/tmp/ikun-auth-isolation-");
  const cfg=config({dataRoot:directory,origin,secure:false});mkdirSync(join(directory,"auth"));
  const path=join(directory,"auth/auth.db"),foreign=new DatabaseSync(path);
  foreign.exec("CREATE TABLE projects(id TEXT)");foreign.close();const before=readFileSync(path);
  assert.throws(()=>new AuthStore(cfg,true));assert.deepEqual(readFileSync(path),before);
  rmSync(path);
  const source=join(directory,"foreign.db"),db=new DatabaseSync(source);db.close();
  symlinkSync(source,path);assert.throws(()=>new AuthStore(cfg,true));rmSync(path);
  linkSync(source,path);assert.throws(()=>new AuthStore(cfg,true));
  rmSync(directory,{recursive:true,force:true});
});

test("foundation auth DB upgrades in place, restarts; scope/checksum mismatch fail closed",async()=>{
  const directory=mkdtempSync("/private/tmp/ikun-auth-migration-");mkdirSync(join(directory,"auth"));
  const path=join(directory,"auth/auth.db"),base=new DatabaseSync(path);
  base.exec(`PRAGMA application_id=${APP_ID};CREATE TABLE _schema_migrations(version INTEGER PRIMARY KEY,name TEXT,applied_at TEXT);
    INSERT INTO _schema_migrations VALUES(1,'foundation','now');CREATE TABLE _store_identity(singleton INTEGER PRIMARY KEY,store_name TEXT);
    INSERT INTO _store_identity VALUES(1,'auth');`);base.close();
  const cfg=config({dataRoot:directory,origin,secure:false});
  assert.throws(()=>new AuthStore(cfg,false),/AUTH_MIGRATION_REQUIRED/);
  let store=new AuthStore(cfg,true);assert.equal(store.db.prepare("SELECT max(version) AS v FROM _schema_migrations").get().v,2);store.close();
  store=new AuthStore(cfg,false);store.close();
  assert.throws(()=>new AuthStore(config({...cfg,tenantId:"other"}),false),/AUTH_SCOPE_MISMATCH/);
  const corrupt=new DatabaseSync(path);corrupt.exec("UPDATE auth_migration_checksums SET checksum='bad'");corrupt.close();
  assert.throws(()=>new AuthStore(cfg,false),/AUTH_MIGRATION_CHECKSUM_MISMATCH/);
  rmSync(directory,{recursive:true,force:true});
});

test("session cap and token collisions are not reused",()=>fixture(async env=>{
  const sessions=[];for(let i=0;i<6;i++) sessions.push(await env.store.login("root_admin",password));
  assert.equal(new Set(sessions.map(s=>s.token)).size,6);
  assert.throws(()=>env.store.authenticate(sessions[0].token),error=>error.status===401);
  assert.ok(env.store.authenticate(sessions[5].token));
}));

test("scope cannot be selected by query; identity includes the bound tenant",()=>fixture(async env=>{
  const {session}=await viewer(env);
  assert.equal(session.data.tenant_id,"ikun-main");
  assert.equal(actor(env,session).tenant_id,"ikun-main");
  for (const query of ["tenant_id=other","tenant_id=ikun-main&tenant_id=other"])
    assert.equal(env.api.gate(request("/api/v1/projects?"+query,"GET",undefined,session)).status,403);
  assert.equal(env.api.gate(request("/settings","GET",undefined,session)).status,403);
}));

test("schema SQL review copy and generated UI match executable sources",()=>{
  const source=readFileSync(new URL("../src/database.ts",import.meta.url),"utf8");
  const sql=source.split("const migration = `")[1].split("`;")[0];
  const review=readFileSync(new URL("../../../schemas/auth/002_accounts.sql",import.meta.url),"utf8");
  assert.equal(review.split("\n").slice(1).join("\n"),sql);
  const generated=readFileSync(new URL("../src/ui.ts",import.meta.url),"utf8");
  assert.ok(generated.includes(JSON.stringify(readFileSync(new URL("../static/auth.js",import.meta.url),"utf8"))));
});

test("SSE closes quiet connection on revocation and cancels upstream",()=>fixture(async env=>{
  const root=await login(env);let cancelled=false;
  const upstream=new Response(new ReadableStream({start(controller){controller.enqueue(new TextEncoder().encode("data: first\n\n"));},cancel(){cancelled=true;}}),
    {headers:{"content-type":"text/event-stream"}});
  const response=env.api.stream(request("/api/v1/projects","GET",undefined,root),upstream),reader=response.body.getReader();
  assert.equal(new TextDecoder().decode((await reader.read()).value),"data: first\n\n");
  env.store.logout(actor(env,root));
  const ended=await Promise.race([reader.read(),delay(2500).then(()=>{throw new Error("SSE did not close");})]);
  assert.ok(ended.done);assert.ok(cancelled);
}));
