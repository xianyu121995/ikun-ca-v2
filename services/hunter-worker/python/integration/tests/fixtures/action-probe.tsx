// Preview-only fixture: deliberately excluded from Proxy so the actual Action must authorize.
import {redirect} from 'next/navigation';
import {confirmHunterMonitoring} from '../../../hunter/actions';
export const dynamic='force-dynamic';
async function submit(form:FormData){
 'use server';
 const result=await confirmHunterMonitoring({discovery_id:String(form.get('discovery_id')),project:JSON.parse(String(form.get('project'))),revision:Number(form.get('revision')),confirmed:true,idempotency_key:String(form.get('key')),csrf_token:String(form.get('csrf'))});
 redirect('/internal/v1/hunter-action-probe?status='+result.status);
}
export default async function Probe({searchParams}:{searchParams:Promise<{status?:string}>}){
 const status=(await searchParams).status;
 return <main><h1>Local synthetic Action fixture</h1><output aria-label="Action result">{status??'ready'}</output><form action={submit}>
  <label>Discovery<input name="discovery_id"/></label><label>Revision<input name="revision"/></label>
  <label>Key<input name="key"/></label><label>CSRF<input name="csrf"/></label><label>Project<textarea name="project"/></label>
  <button type="submit">Execute fixture action</button>
 </form></main>;
}
