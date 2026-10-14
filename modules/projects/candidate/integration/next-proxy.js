/** Opt-in candidate for Next.js 16 proxy.js. Install only during agreed website integration.
 * It forwards HTTP to the projects domain, never opens SQLite or supplies user roles.
 */
import {NextResponse} from 'next/server';

const FORWARDED = ['accept','content-type','authorization','cookie','origin','x-csrf-token','idempotency-key','x-request-id'];
function failure(status,code,message){
  return Response.json({error:{code,message,retryable:status===502},request_id:crypto.randomUUID()},
    {status,headers:{'cache-control':'no-store'}});
}

export async function proxy(request){
  const configured=process.env.PROJECTS_API_URL;
  if(!configured)return NextResponse.next();
  let backend,origin;
  try{
    backend=new URL(configured);
    origin=new URL(process.env.PROJECTS_PUBLIC_ORIGIN||'');
    if(backend.protocol!=='http:'||!['127.0.0.1','localhost','[::1]'].includes(backend.hostname)
       ||backend.username||backend.password||backend.pathname!=='/'||backend.search||backend.hash
       ||!['http:','https:'].includes(origin.protocol)||origin.username||origin.password
       ||origin.pathname!=='/'||origin.search||origin.hash)throw new Error('invalid configuration');
  }catch{return failure(503,'projects_not_configured','主页服务配置无效');}
  if(request.headers.get('host')!==origin.host)return failure(400,'invalid_host','请求主机不受信任');
  const headers=new Headers();
  for(const name of FORWARDED){const value=request.headers.get(name);if(value)headers.set(name,value);}
  headers.set('host',origin.host);
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
  try{
    let body;
    if(!['GET','HEAD'].includes(request.method)&&request.body){
      const reader=request.body.getReader(),chunks=[];
      controller.signal.addEventListener('abort',()=>{void reader.cancel();},{once:true});
      let size=0;
      while(true){
        const {value,done}=await reader.read();if(done)break;
        size+=value.byteLength;
        if(size>48*1024){await reader.cancel();return failure(413,'body_too_large','资料大小超过限制');}
        chunks.push(value);
      }
      if(controller.signal.aborted)throw new Error('request timeout');
      body=new Uint8Array(size);let offset=0;for(const chunk of chunks){body.set(chunk,offset);offset+=chunk.byteLength;}
    }
    const path=request.nextUrl.pathname+request.nextUrl.search;
    const result=await fetch(new URL(path,backend),{method:request.method,headers,body,redirect:'manual',signal:controller.signal,cache:'no-store'});
    // Homepage responses are bounded by page/field limits; do not leak hop-by-hop headers.
    const output=new Headers();
    for(const name of ['content-type','content-security-policy','cache-control','x-content-type-options','referrer-policy','x-frame-options','x-request-id','retry-after','etag']){
      const value=result.headers.get(name);if(value)output.set(name,value);
    }
    for(const cookie of result.headers.getSetCookie())output.append('set-cookie',cookie);
    const empty=request.method==='HEAD'||[204,205,304].includes(result.status);
    return new Response(empty?null:await result.arrayBuffer(),{status:result.status,headers:output});
  }catch{return failure(502,'projects_unavailable','主页服务暂时不可用，请稍后重试');}
  finally{clearTimeout(timeout);}
}

export const config={matcher:['/','/assets/home.css','/assets/home.js','/api/home/:path*']};
