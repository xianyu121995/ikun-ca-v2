/** Synthetic isolated B1 accounts, never imported by the website. */
import {writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const preview=new URL('../../.preview/',import.meta.url);
const {config}=await import(new URL('modules/auth/dist/src/config.js',preview));
const {LocalAccounts}=await import(new URL('modules/auth/dist/src/local.js',preview));
const [dataRoot,origin,output]=process.argv.slice(2);
const store=new LocalAccounts(config({dataRoot,origin,secure:false}),true);
const initial='Synthetic-B2-Initial-984!';const password='Synthetic-B2-Final-274!';
await store.bootstrap('testadmin',initial);await store.create('testuser',initial);await store.create('forceduser',initial);
for(const username of ['testadmin','testuser']){const login=await store.login(username,initial);await store.changePassword(login.actor,initial,password);}
writeFileSync(output,JSON.stringify({admin:{username:'testadmin',password},user:{username:'testuser',password},forced:{username:'forceduser',password:initial}}),{mode:0o600});store.close();
