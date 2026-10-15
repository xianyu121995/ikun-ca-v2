import {probeProjectsIpc} from '@ikun/runtime';
import {inspectAuthDatabase} from '../../../modules/auth/dist/src/database.js';
import {environment} from '../../../modules/auth/dist/src/config.js';
/** Exact B1 schema admission; no generic version widening and no Node projects DB access. */
export async function websiteReady():Promise<boolean>{
  try{
    if(!inspectAuthDatabase(environment()))return false;
    const socketPath=process.env.IKUN_PROJECTS_IPC_SOCKET,token=process.env.IKUN_PROJECTS_IPC_TOKEN,buildSha=process.env.IKUN_PROJECTS_BUILD_SHA;
    if(!socketPath||!token||!buildSha)return false;
    return probeProjectsIpc({socketPath,token,buildSha});
  }catch{return false;}
}
