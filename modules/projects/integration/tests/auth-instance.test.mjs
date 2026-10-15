import {after,test} from 'node:test';
import assert from 'node:assert/strict';
import {cpSync,mkdirSync,mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

// Two real compiled B1 module copies model separate Next bundles. No DB is opened.
const scratch=mkdtempSync('/private/tmp/ikun-projects-auth-class-');
writeFileSync(join(scratch,'package.json'),' {"type":"module"}\n');
for(const bundle of ['a','b']){
  const root=join(scratch,bundle);mkdirSync(join(root,'apps/website/lib'),{recursive:true});
  cpSync(fileURLToPath(new URL('../../.preview/modules/auth/dist',import.meta.url)),join(root,'modules/auth/dist'),{recursive:true});
  writeFileSync(join(root,'apps/website/lib/projects.ts'),readFileSync(new URL('../website/lib/projects.ts',import.meta.url)));
}
const A=await import(pathToFileURL(join(scratch,'a/modules/auth/dist/src/http.js')));
const B=await import(pathToFileURL(join(scratch,'b/modules/auth/dist/src/http.js')));
const {AuthError}=await import(pathToFileURL(join(scratch,'a/modules/auth/dist/src/security.js')));
const {AuthError:ErrorB}=await import(pathToFileURL(join(scratch,'b/modules/auth/dist/src/security.js')));
const {projectsAuth}=await import(pathToFileURL(join(scratch,'b/apps/website/lib/projects.ts')));
const previous={auth:globalThis.ikunAuth,policy:globalThis.ikunProjectsPolicy};
after(()=>{globalThis.ikunAuth=previous.auth;globalThis.ikunProjectsPolicy=previous.policy;rmSync(scratch,{recursive:true,force:true});});
const origin='http://127.0.0.1:31998';
const readApi=[/^\/api\/v1\/projects$/,/^\/api\/v1\/tracking\/latest$/];
const readPages=[/^\/$/,/^\/tracking$/];
function request(path,method='GET',csrf='fixture-csrf'){
  return new Request(origin+path,{method,headers:{host:new URL(origin).host,origin,'content-type':'application/json','x-csrf-token':csrf}});
}
function fixture(ErrorClass=AuthError){
  let state='valid',role='user';
  const store={cfg:{origin,secure:false,tenantId:'ikun-main'},authenticate(){
    if(state==='unexpected')throw Error('synthetic unexpected failure');
    if(state!=='valid')throw new ErrorClass(401,'UNAUTHENTICATED','synthetic '+state);
    return {id:'fixture_user',username:'fixture_user',tenant_id:'ikun-main',role,must_change_password:false,csrf_token:'fixture-csrf'};
  }};
  return {store,setState(value){state=value;},setRole(value){role=value;}};
}

test('Control: real cross-module AuthError mismatch reproduces 500; same module returns 303',()=>{
  const f=fixture();f.setState('revoked');
  assert.equal(new A.AuthHttp(f.store,readApi,readPages).gate(request('/tracking')).status,303);
  assert.equal(new B.AuthHttp(f.store,readApi,readPages).gate(request('/tracking')).status,500);
});

for(const topology of ['same','cross'])test('Projects preserves '+topology+' bundle constructor, singleton and permissions',()=>{
  const Http=topology==='same'?B.AuthHttp:A.AuthHttp;
  const ErrorClass=topology==='same'?ErrorB:AuthError;
  const f=fixture(ErrorClass);const initial=new Http(f.store,readApi,readPages);
  globalThis.ikunAuth=initial;globalThis.ikunProjectsPolicy=false;
  const http=projectsAuth();assert.equal(http.constructor,initial.constructor);assert.equal(http.store,f.store);
  for(const path of ['/','/tracking','/tracking/child','/unexpected'])assert.equal(http.readPages.some(rule=>rule.test(path)),initial.readPages.some(rule=>rule.test(path)));
  const count=http.readApi.length;for(let i=0;i<5;i++)assert.equal(projectsAuth(),http);assert.equal(http.readApi.length,count);
  assert.equal(http.gate(request('/api/v1/projects/home-summary')),null);
  assert.equal(http.gate(request('/api/v1/projects/milestones')),null);
  assert.equal(http.gate(request('/api/v1/projects/operations/550e8400-e29b-41d4-a716-446655440000')),null);
  assert.equal(http.gate(request('/api/v1/projects/operations/not-a-uuid')).status,403);
  assert.equal(http.gate(request('/api/v1/tracking/latest')),null);
  assert.equal(http.gate(request('/api/v1/projects','POST')).status,403);
  f.setRole('superadmin');assert.equal(http.gate(request('/api/v1/projects','POST')),null);
  assert.equal(http.gate(request('/api/v1/projects','POST','wrong')).status,403);
  for(const reason of ['anonymous','disabled','logout','expired','password_changed']){
    f.setState(reason);assert.equal(http.gate(request('/tracking')).status,303);
    assert.equal(http.gate(request('/api/v1/projects/home-summary')).status,401);
  }
  f.setState('unexpected');assert.equal(http.gate(request('/tracking')).status,500);
});
