/** Activate only the fresh direct-entry fixture through accepted B1 public methods. */
import {readFileSync,writeFileSync} from 'node:fs';
import {randomBytes} from 'node:crypto';
import {LocalAccounts} from '../../modules/auth/dist/src/local.js';
import {config} from '../../modules/auth/dist/src/config.js';
const [dataRoot,origin,path]=process.argv.slice(2);
const accounts=JSON.parse(readFileSync(path,'utf8'));
const store=new LocalAccounts(config({dataRoot,origin,secure:false}));
try{
 for(const role of ['admin','user']){
  const account=accounts[role];const session=await store.login(account.username,account.password);
  const next=randomBytes(24).toString('base64url');
  await store.changePassword(session.actor,account.password,next);account.password=next;
 }
 writeFileSync(path,JSON.stringify(accounts),{mode:0o600});
}finally{store.close();}
