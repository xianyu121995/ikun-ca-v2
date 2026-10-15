// Synthetic Auth fixture using the frozen B1 owner, never direct cross-library SQL.
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const preview=process.env.B4_PREVIEW_ROOT;
const {LocalAccounts}=await import(pathToFileURL(path.join(preview,'modules/auth/dist/src/local.js')));
const {config}=await import(pathToFileURL(path.join(preview,'modules/auth/dist/src/config.js')));
const cfg=config({dataRoot:process.env.DATA_ROOT,origin:process.env.IKUN_AUTH_ORIGIN,secure:false});
const action=process.argv[2]||'seed';
const store=new LocalAccounts(cfg,action==='seed');
try{
 if(action==='seed'){
  await store.bootstrap('fixture_admin','B4-fixture-initial-passphrase');
  await store.create('fixture_reader','B4-fixture-initial-passphrase');
 }else if(action==='disable')store.setEnabled(process.argv[3],false);
 else if(action==='enable')store.setEnabled(process.argv[3],true);
 else throw Error('Unsupported fixture operation');
}finally{store.close();}
