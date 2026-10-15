import {randomUUID} from 'node:crypto';
import {withAuth,requireIdentity} from '../../../modules/auth/dist/src/server.js';
import {ipc,projectsAuth,failure,requestId} from './projects';

export async function projectEvents(request:Request){
  projectsAuth();const id=requestId(request);const headers=new Headers(request.headers);headers.set('x-request-id',id);request=new Request(request,{headers});
  return withAuth(request,async()=>{
    const principal=requireIdentity(request);const url=new URL(request.url);
    if(url.searchParams.size)return failure(id,422,'VALIDATION_ERROR','事件流不接受查询参数');
    const last=request.headers.get('last-event-id')??'0';if(!/^\d{1,15}$/.test(last))return failure(id,422,'VALIDATION_ERROR','事件游标不正确');
    let after=last,stopped=false,heartbeat=Date.now(),timer:ReturnType<typeof setTimeout>|undefined;
    const abort=new AbortController();const encoder=new TextEncoder();
    const body=new ReadableStream<Uint8Array>({
      start(controller){
        const stop=()=>{if(stopped)return;stopped=true;clearTimeout(timer);abort.abort();try{controller.close();}catch{}};
        request.signal.addEventListener('abort',stop,{once:true});
        async function poll(){
          if(stopped)return;
          try{
            const response=await ipc({operation:'changes',principal,request_id:randomUUID(),query:{after}},abort.signal);
            if(!response.ok){stop();return;}
            const result=await response.json();
            for(const item of result.data.items){if(stopped)return;after=String(item.sequence);controller.enqueue(encoder.encode(`id: ${after}\nevent: project.updated\ndata: ${JSON.stringify(item.data)}\n\n`));}
            if(Date.now()-heartbeat>=15000){heartbeat=Date.now();controller.enqueue(encoder.encode(': heartbeat\n\n'));}
          }catch{stop();return;}
          if(!stopped)timer=setTimeout(poll,500);
        }
        controller.enqueue(encoder.encode(': connected\n\n'));void poll();
      },
      cancel(){stopped=true;clearTimeout(timer);abort.abort();},
    });
    // B1 withAuth wraps this stream and revalidates quiet streams every second.
    return new Response(body,{headers:{'content-type':'text/event-stream','cache-control':'no-store','x-accel-buffering':'no','x-request-id':id}});
  });
}
