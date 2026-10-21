import type {TrackingVoiceController} from '@ikun/ui';
type Target=Pick<Window,'navigator'|'localStorage'>;
/** Web Locks elect exactly one eligible page. The lock is released on mute, disconnect or page teardown. */
export function bindVoiceOwner(controller:TrackingVoiceController,target:Target=window){
  let leader=false,lease:AbortController|null=null,disposed=false;
  const update=()=>{
    const s=controller.getSnapshot();const eligible=s.enabled&&s.armed&&s.connected&&s.available==='available'&&
      !['failed','quiet-hours','signed-out'].includes(s.status);
    if(!eligible){lease?.abort();lease=null;leader=false;return;}
    if(lease||disposed||!target.navigator.locks)return;
    const active=new AbortController();lease=active;
    void target.navigator.locks.request('ikun.voice.speaker.v1',{signal:active.signal},async()=>{
      if(active.signal.aborted)return;
      leader=true;
      await new Promise<void>(resolve=>{if(active.signal.aborted)resolve();else active.signal.addEventListener('abort',()=>resolve(),{once:true});});
      leader=false;
    }).catch(()=>{});
  };
  const unsubscribe=controller.subscribe(update);update();
  return {isLeader:()=>leader&&!disposed,
    claim(user:string,id:string,serverAt:number,accept:()=>boolean){
      if(!leader||disposed)return false;
      try{
        const key='ikun.voice.spoken.v1.'+encodeURIComponent(user);
        const value=JSON.parse(target.localStorage.getItem(key)??'[]');
        if(!Array.isArray(value))return false;
        const recent=value.filter(r=>r&&typeof r.id==='string'&&typeof r.until==='number'&&r.until>serverAt);
        if(recent.some(r=>r.id===id)||recent.length>=2048)return false;
        recent.push({id,until:serverAt+600_000});target.localStorage.setItem(key,JSON.stringify(recent));return accept();
      }catch{return false;}
    },
    dispose(){disposed=true;leader=false;lease?.abort();lease=null;unsubscribe();}};
}
