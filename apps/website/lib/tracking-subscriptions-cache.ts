import {clearClientSession,invalidateClientData,peekClientData,readClientData} from './client-session-cache';
export type TrackingSubscription={subscription_id:string;project_id:string;x_handle:string;name:string;desired_state:string;notes:string;revision:number;observed_state:string;operation_state:string;connection:string;error_code?:string;rating?:'S'|'A'|'B'|null};
const KEY='tracking:subscriptions';
export function invalidateTrackingSubscriptions(userId:string){invalidateClientData(userId,KEY);}
export function peekTrackingSubscriptions(userId:string){return peekClientData<TrackingSubscription[]>(userId,KEY);}
/** One shared complete projection, including historical subscriptions, for all page and voice consumers. */
export function loadTrackingSubscriptions(userId:string,fresh=false):Promise<TrackingSubscription[]>{
 return readClientData(userId,KEY,async()=>{
  const rows:TrackingSubscription[]=[];let cursor:string|null=null;const seen=new Set<string>();
  do{
   const response:Response=await fetch('/api/v1/tracking/subscriptions?limit=1000&include_removed=true'+(cursor?'&cursor='+encodeURIComponent(cursor):''),{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(12_000)});
   if(!response.ok){if(response.status===401||response.status===403)clearClientSession();throw Error('SUBSCRIPTIONS_UNAVAILABLE');}
   const value:{items:TrackingSubscription[];next_cursor?:string|null}=(await response.json()).data;if(!Array.isArray(value?.items))throw Error('INVALID_SUBSCRIPTIONS');rows.push(...value.items);
   cursor=value.next_cursor??null;if(cursor){if(seen.has(cursor)||seen.size>=100)throw Error('SUBSCRIPTIONS_CURSOR_LOOP');seen.add(cursor);}
  }while(cursor);return rows;
 },fresh?750:30_000);
}
