'use server';
import {requireSuperadminAction} from '../lib/auth';
import {ipc,projectsAuth} from '../lib/projects';
/** Same transaction and UUID receipt as HTTP; no action-only permission bypass. */
export async function createProjectAction(csrf:string,idempotencyKey:string,fields:Record<string,unknown>){
  projectsAuth();const principal=await requireSuperadminAction(csrf);
  const response=await ipc({operation:'create',principal,request_id:crypto.randomUUID(),idempotency_key:idempotencyKey,body:fields});
  return {status:response.status,envelope:await response.json()};
}
