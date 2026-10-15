import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const B0='85be3bd6dce25d82033b6cb1a7157aaa39bd571e';
const root=new URL('../../../',import.meta.url);
const source=execFileSync('git',['show',`${B0}:packages/runtime/src/stores.ts`],{cwd:root,encoding:'utf8'});
const foundation=source.match(/const FOUNDATION_SCHEMA = `([\s\S]*?)`;/)?.[1];
if (!foundation) throw new Error('PINNED_FOUNDATION_SCHEMA_NOT_FOUND');
const legacySource=execFileSync('git',['show','aa3cf65ce5c24cc293e0daec279659d2cc080c5f:modules/auth/src/database.ts'],{cwd:root,encoding:'utf8'});
const legacy=legacySource.match(/const migration = `([\s\S]*?)`;/)?.[1];
if (!legacy) throw new Error('PINNED_LEGACY_SCHEMA_NOT_FOUND');
const canonical=readFileSync(new URL('../../../schemas/auth/002_accounts.sql',import.meta.url),'utf8');
const values={B0_COMMIT:B0,FOUNDATION_SQL:foundation,FOUNDATION_CHECKSUM:createHash('sha256').update(foundation).digest('hex'),
  MIGRATION_SQL:canonical,MIGRATION_CHECKSUM:createHash('sha256').update(canonical).digest('hex'),
  LEGACY_SQL:legacy,LEGACY_CHECKSUM:createHash('sha256').update(legacy).digest('hex')};
writeFileSync(new URL('../src/schema.ts',import.meta.url),'// Generated from pinned B0 and schemas/auth/002_accounts.sql; do not hand-edit.\n'+
  Object.entries(values).map(([key,value])=>`export const ${key} = ${JSON.stringify(value)};`).join('\n')+'\n');
