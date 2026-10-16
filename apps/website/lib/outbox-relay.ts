import {randomUUID} from 'node:crypto';
import {ipc} from './projects';

export interface RelayConfig{origin:string;token:string}
function checked(config:RelayConfig){const url=new URL(config.origin);if(url.protocol!=='http:'||!['127.0.0.1','[::1]'].includes(url.hostname)||url.username||url.password||url.pathname!=='/'||url.search||url.hash||config.token.length<32)throw Error('INVALID_TRACKING_TARGET');return url.origin;}
/** Invoked by the website owner's scheduler. No standalone worker, DB reader or collection. */
export async function relayOnce(config:RelayConfig,target?:string){
  const origin=checked(config);const request_id=randomUUID();
  const claim=await ipc({operation:'outbox_claim',source:'tracking',target,request_id});
  if(!claim.ok)return false;const item=(await claim.json()).data.item;if(!item)return false;
  const command=item.command;let outcome='unknown',result:unknown;
  try{
    // Unknown delivery is ALWAYS reconciled by its original command ID first.
    if(item.action==='send'&&command.operation==='tracking.remove'&&!command.subscription_id){
      let cursor:string|null=null,found: {project_id:string;subscription_id:string;revision:number}|undefined;
      do {
        const response:Response=await fetch(origin+'/internal/v1/subscriptions?include_removed=true&limit=100'+(cursor?'&cursor='+encodeURIComponent(cursor):''),{headers:{authorization:'Bearer '+config.token,'x-request-id':request_id},signal:AbortSignal.timeout(5000),cache:'no-store'});
        if(!response.ok)throw Error('CLEANUP_LOOKUP_FAILED');
        const page:{items:{project_id:string;subscription_id:string;revision:number}[];next_cursor:string|null}=(await response.json()).data;found=page.items.find((r:{project_id:string})=>r.project_id===command.project_id);cursor=page.next_cursor;
      }while(cursor&&!found);
      if(!found){
        const result={command_id:command.command_id,state:'succeeded',project_id:command.project_id,subscription_id:null,revision:null,updated_at:new Date().toISOString(),error_code:null,request_id};
        await ipc({operation:'outbox_result',source:'tracking',target:command.command_id,request_id,body:{lease_token:item.lease_token,outcome:'received',result}});return true;
      }
      command.subscription_id=found.subscription_id;command.expected_revision=found.revision;
    }
    const path=item.action==='send'?'/internal/v1/commands':'/internal/v1/commands/'+encodeURIComponent(command.command_id);
    const response=await fetch(origin+path,{method:item.action==='send'?'POST':'GET',headers:{authorization:'Bearer '+config.token,'content-type':'application/json','x-request-id':request_id},
      ...(item.action==='send'?{body:JSON.stringify(command)}:{}),signal:AbortSignal.timeout(5000),redirect:'error',cache:'no-store'});
    if(item.action==='reconcile'&&response.status===404){const value=await response.json();if(value?.error?.code==='NOT_FOUND'&&typeof value.request_id==='string')outcome='not_found';}
    else if(response.ok){const value=await response.json();if(value?.data){outcome='received';result=value.data;}}
  }catch{/* Preserve unknown. The persisted lease/command controls the next attempt. */}
  await ipc({operation:'outbox_result',source:'tracking',target:command.command_id,request_id,body:{lease_token:item.lease_token,outcome,...(result?{result}:{})}});
  return true;
}
