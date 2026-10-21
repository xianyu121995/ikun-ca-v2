import type {PublishedVoiceActivity} from '@ikun/ui';
export const PUBLISHED_VOICE_PATH='/api/v1/tracking/latest?profile=published-v1&ratings=S,A,B&limit=100';
const activity=/^act_[0-9a-f]{8}-[0-9a-f]{4}-[45][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
type FeedRow={activity_id:string;subscription_id:string;project_id:string;name:string;rating:'S'|'A'|'B';occurred_at:string|null};
type FeedEnvelope={request_id:string;data?:{profile:string;items:FeedRow[];next_cursor:string|null}};
type Options={request?:typeof fetch;onItem:(item:PublishedVoiceActivity,serverAt:number)=>void;connected:(value:boolean)=>void;revoke:()=>void};
/** One initial baseline per page. SSE refreshes immediately; overlapping reads coalesce with a trailing read. */
export class PublishedVoiceFeed {
  private seen=new Set<string>();private initialized=false;private stopped=false;private pending:Promise<void>|null=null;private again=false;
  private abort=new AbortController();private view='qv1_'+crypto.randomUUID();
  constructor(private readonly options:Options){}
  refresh():Promise<void>{
    if(this.stopped)return Promise.resolve();
    if(this.pending){this.again=true;return this.pending;}
    this.pending=this.read().finally(()=>{this.pending=null;if(this.again&&!this.stopped){this.again=false;void this.refresh();}});
    return this.pending;
  }
  private async read(){
    try{
      const items:{item:PublishedVoiceActivity;serverAt:number}[]=[];let cursor:string|null=null;
      do{
        const response:Response=await (this.options.request??fetch)(PUBLISHED_VOICE_PATH+(cursor?'&cursor='+encodeURIComponent(cursor):''),{
          credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.any([this.abort.signal,AbortSignal.timeout(8000)]),headers:{'x-tracking-query-view':this.view}});
        if(response.status===401||response.status===403){this.stop();this.options.revoke();return;}
        if(!response.ok)throw Error('feed_unavailable');
        const serverAt=Date.parse(response.headers.get('x-ikun-server-time')??'');const envelope:FeedEnvelope=await response.json();const data=envelope?.data;
        if(this.stopped)return;
        if(!Number.isFinite(serverAt)||!data||data.profile!=='published-v1'||!Array.isArray(data.items)||data.items.length>100)throw Error('invalid_feed');
        let old=false;
        for(const row of data.items){
          if(typeof row.activity_id!=='string'||!activity.test(row.activity_id))throw Error('invalid_activity');
          const occurred=Date.parse(row.occurred_at??'');const age=serverAt-occurred;
          if(Number.isFinite(occurred)&&age>600_000)old=true;
          // No browser wall-clock comparison; missing/old/future dates are visible but silent.
          items.push({item:{activity_id:row.activity_id,subscription_id:row.subscription_id,project_id:row.project_id,
            name:row.name,rating:row.rating,age_ms:Number.isFinite(occurred)?age:Infinity},serverAt});
        }
        cursor=!old&&typeof data.next_cursor==='string'?data.next_cursor:null;
        if(items.length>=2000)throw Error('feed_overload');
      }while(cursor);
      if(this.stopped)return;
      this.options.connected(true);
      const baseline=!this.initialized;this.initialized=true;
      for(const {item,serverAt} of items.reverse()){
        if(this.seen.has(item.activity_id))continue;
        this.seen.add(item.activity_id);
        if(!baseline&&Number.isFinite(item.age_ms)&&item.age_ms>=0&&item.age_ms<=600_000)this.options.onItem(item,serverAt);
      }
      // IDs in the recent list stay remembered for this page; never replay after a refresh/update.
    }catch{if(!this.stopped)this.options.connected(false);}
  }
  stop(){this.stopped=true;this.again=false;this.abort.abort();}
}
