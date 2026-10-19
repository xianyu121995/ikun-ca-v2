export type TrackingSubscription = {subscription_id:string;project_id:string;x_handle:string;name:string;desired_state:string};
const TTL=30_000;
let cached:{userId:string;expires:number;promise:Promise<TrackingSubscription[]>}|undefined;
export function invalidateTrackingSubscriptions(userId:string){if(cached?.userId===userId)cached=undefined;}
/** One in-flight read per account; consumers unmount independently without aborting each other. */
export function loadTrackingSubscriptions(userId:string):Promise<TrackingSubscription[]>{
  if(cached?.userId===userId&&cached.expires>Date.now())return cached.promise;
  const entry={userId,expires:Infinity,promise:Promise.resolve([] as TrackingSubscription[])};
  entry.promise=(async()=>{
    const rows:TrackingSubscription[]=[];let cursor:string|null=null;const seen=new Set<string>();
    do{
      const response:Response=await fetch('/api/v1/tracking/subscriptions?limit=100'+(cursor?'&cursor='+encodeURIComponent(cursor):''),{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(10_000)});
      if(!response.ok)throw Error('SUBSCRIPTIONS_UNAVAILABLE');
      const value:{items:TrackingSubscription[];next_cursor?:string|null}=(await response.json()).data;
      rows.push(...value.items.map((row:TrackingSubscription)=>({subscription_id:row.subscription_id,project_id:row.project_id,x_handle:row.x_handle,name:row.name,desired_state:row.desired_state})));
      cursor=value.next_cursor??null;
      if(cursor){if(seen.has(cursor))throw Error('SUBSCRIPTIONS_CURSOR_LOOP');seen.add(cursor);}
    }while(cursor);
    entry.expires=Date.now()+TTL;return rows;
  })().catch(error=>{if(cached===entry)cached=undefined;throw error;});
  cached=entry;return entry.promise;
}
