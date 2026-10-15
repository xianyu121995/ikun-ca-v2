export async function register(){
  if(process.env.NEXT_RUNTIME==='nodejs'){
    const {startRelay}=await import('./lib/service-gateway/relay');
    startRelay();
  }
}
