'use server';
import {randomUUID} from 'node:crypto';
import {headers} from 'next/headers';
import {requireSuperadminAction} from '../../lib/auth';
import {hunterCall} from '../../lib/hunter';
import {auth,withAuth} from '../../../../modules/auth/dist/src/server.js';

export async function confirmHunterMonitoring(input:{discovery_id:string;project:unknown;revision:number;confirmed:true;idempotency_key:string;csrf_token:string}){
  const requestId=randomUUID(),incoming=new Headers(await headers());
  incoming.set('content-type','application/json');incoming.set('x-csrf-token',input.csrf_token);
  const request=new Request(new URL('/actions/business',auth().store.cfg.origin),{method:'POST',headers:incoming});
  const response=await withAuth(request,async()=>{
   const principal=await requireSuperadminAction(input.csrf_token);
   if(!/^dsc_[a-f0-9-]{36}$/.test(input.discovery_id)||input.confirmed!==true||!Number.isSafeInteger(input.revision)||input.revision<1)return Response.json({error:{code:'VALIDATION_ERROR',message:'人工确认资料无效',retryable:false},request_id:requestId},{status:422});
   return hunterCall('/api/v1/hunter/discoveries/'+input.discovery_id+'/monitoring-requests',requestId,principal,'POST',{confirmed:true,project:input.project},{'if-match':'"rev-'+input.revision+'"','idempotency-key':input.idempotency_key});
  });
  return {status:response.status,...await response.json()};
}
