import {mkdtempSync,rmSync} from 'node:fs';
import {LocalAccounts} from '../dist/src/local.js';
import {AuthHttp} from '../dist/src/http.js';
import {config,cookieName} from '../dist/src/config.js';
export const origin='http://127.0.0.1:3600';
export const initial='unit-test-initial-long-passphrase',password='unit-test-active-long-passphrase',changed='unit-test-changed-long-passphrase';
export async function fixture(run,overrides={}) {
 const directory=mkdtempSync('/private/tmp/ikun-auth-final-');let now=1800000000;
 const cfg=config({dataRoot:directory,origin,secure:false,...overrides});let store=new LocalAccounts(cfg,true,()=>now);
 await store.bootstrap('root_admin',initial);const first=await store.login('root_admin',initial);
 const root=await store.changePassword(first.actor,initial,password);
 const build=()=>new AuthHttp(store,[/^\/api\/v1\/projects(?:\/[^/]+)?$/],[/^\/$/,/^\/hunter$/, /^\/tracking$/]);let api=build();
 const env={directory,dir:directory,cfg,root,get store(){return store;},get api(){return api;},advance(seconds){now+=seconds;},restart(){store.close();store=new LocalAccounts(cfg,false,()=>now);api=build();}};
 try{await run(env);}finally{store.close();rmSync(directory,{recursive:true,force:true});}
}
export function req(path,method='GET',data,session,extra={}) {
 const headers={host:new URL(origin).host,...extra};
 if(session){headers.cookie=`ikun_dev_session=${session.token}`;headers['x-csrf-token']=session.actor.csrf_token;}
 if(data!==undefined){headers.origin=origin;headers['content-type']='application/json';}
 return new Request(origin+path,{method,headers,...(data===undefined?{}:{body:JSON.stringify(data)})});
}
export async function user(e,name='viewer') {
 const record=await e.store.create(name,initial),first=await e.store.login(name,initial);
 const logged=await e.store.changePassword(first.actor,initial,password);return {record,logged};
}
