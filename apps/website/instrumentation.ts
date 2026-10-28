export async function register(){
  if(process.env.NEXT_RUNTIME==='nodejs'){
    const {installShutdown}=await import('./lib/shutdown');
    installShutdown();
    const {startRelay}=await import('./lib/service-gateway/relay');
    startRelay();
  }
}
