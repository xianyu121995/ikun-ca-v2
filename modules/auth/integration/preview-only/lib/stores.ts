/** B1 isolated fixture ONLY. Chief must review a separate real readiness patch. */
import {inspectStores,closeStores,storesHealthy} from '@ikun/runtime';
import {environment} from '../../../modules/auth/dist/src/config.js';
import {inspectAuthDatabase} from '../../../modules/auth/dist/src/database.js';
export async function websiteReady():Promise<boolean> {
  const cfg=environment();
  const stores=inspectStores('website',cfg.dataRoot,{names:['auth'],maximumVersion:2});
  try {return storesHealthy(stores)&&inspectAuthDatabase(cfg);} finally {closeStores(stores);}
}
