import type {TrackingVoiceController} from '@ikun/ui';
type Target=Pick<Window,'navigator'|'localStorage'>;
/** One eligible page owns the speaker. Non-blocking election avoids accumulating work in follower tabs. */
export function bindVoiceOwner(controller:TrackingVoiceController,target:Target=window){
  let leader=false,lease:AbortController|null=null,disposed=false,ready=Promise.resolve();
  const update=()=>{
    const s=controller.getSnapshot();const eligible=s.enabled&&s.armed&&s.connected&&s.available==='available'&&
      !['failed','quiet-hours','signed-out'].includes(s.status);
    if(!eligible){lease?.abort();lease=null;leader=false;return;}
    if(lease||disposed||!target.navigator.locks)return;
    const active=new AbortController();lease=active;
    let settled!:()=>void;ready=new Promise<void>(resolve=>{settled=resolve;});
    // Web Locks forbids signal + ifAvailable; cancellation is handled by the callback below.
    void target.navigator.locks.request('ikun.voice.speaker.v1',{ifAvailable:true},async lock=>{
      if(!lock||active.signal.aborted)return;
      leader=true;settled();
      await new Promise<void>(resolve=>{if(active.signal.aborted)resolve();else active.signal.addEventListener('abort',()=>resolve(),{once:true});});
      leader=false;
    }).catch(()=>{}).finally(()=>{settled();if(lease===active)lease=null;});
  };
  const unsubscribe=controller.subscribe(update);update();
  return {isLeader:()=>leader&&!disposed,
    async claim(user:string,id:string,serverAt:number,accept:()=>boolean){
      if(disposed)return false;
      update();const attempt=lease;await ready;
      if(!leader||disposed||lease!==attempt)return false;
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
