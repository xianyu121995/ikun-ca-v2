import assert from 'node:assert/strict';
import {test} from 'node:test';
import {fixture,password,req} from './helpers.mjs';
import {clientPeer} from '../dist/src/server.js';
test('a new device revokes the previous device across restart',()=>fixture(async e=>{
 const newer=await e.store.login('root_admin',password);
 assert.equal((await e.api.handle(req('/api/v1/auth/me','GET',undefined,e.root))).status,401);
 assert.equal((await e.api.handle(req('/api/v1/auth/me','GET',undefined,newer))).status,200);
 e.restart();
 assert.equal((await e.api.handle(req('/api/v1/auth/me','GET',undefined,e.root))).status,401);
 assert.equal((await e.api.handle(req('/api/v1/auth/me','GET',undefined,newer))).status,200);
},{maxSessions:1}));
test('Cloudflare client address wins over a forwarded address',()=>{
 assert.equal(clientPeer(new Request('https://v2.ikun.ca',{headers:{'cf-connecting-ip':'203.0.113.7','x-forwarded-for':'198.51.100.8'}})),'203.0.113.7');
});
