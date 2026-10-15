import {relayOnce} from '../outbox-relay';

const state=globalThis as typeof globalThis & {ikunRelayStop?:()=>void};
/** One in-process call at a time. Original leases and bounded RPCs own in-flight recovery. */
export function startRelay(){
  if(state.ikunRelayStop||!process.env.TRACKING_API_URL||!process.env.TRACKING_API_TOKEN)return;
  const config={origin:process.env.TRACKING_API_URL,token:process.env.TRACKING_API_TOKEN};
  let stopped=false,timer:ReturnType<typeof setTimeout>|undefined;
  const stop=()=>{stopped=true;clearTimeout(timer);};
  state.ikunRelayStop=stop;
  process.once('SIGTERM',stop);process.once('SIGINT',stop);
  async function tick(){
    if(stopped)return;
    try{await relayOnce(config);}catch{/* Persisted lease/unknown is reconciled by the original relay. */}
    if(!stopped){timer=setTimeout(()=>void tick(),1000);timer.unref();}
  }
  timer=setTimeout(()=>void tick(),1000);timer.unref();
}
