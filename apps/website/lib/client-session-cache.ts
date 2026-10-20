/** Document-memory only. Never caches credentials or authorizes a write. */
type Entry={value?:unknown;at:number;promise?:Promise<unknown>};
const entries=new Map<string,Entry>();let account:string|null=null;
export function clearClientSession(){entries.clear();account=null;}
export function useClientAccount(id:string){if(account!==null&&account!==id)entries.clear();account=id;}
function key(id:string,path:string){useClientAccount(id);return JSON.stringify([id,path]);}
export function peekClientData<T>(id:string,path:string):T|undefined{return entries.get(key(id,path))?.value as T|undefined;}
export function saveClientData<T>(id:string,path:string,value:T){const k=key(id,path);entries.set(k,{value,at:Date.now()});if(entries.size>100)entries.delete(entries.keys().next().value!);}
export function invalidateClientData(id:string,prefix=''){for(const k of entries.keys()){const [owner,path]=JSON.parse(k);if(owner===id&&path.startsWith(prefix))entries.delete(k);}}
export function readClientData<T>(id:string,path:string,load:()=>Promise<T>,freshFor=0):Promise<T>{
 const k=key(id,path),old=entries.get(k);
 if(old?.promise)return old.promise as Promise<T>;
 if(old&&old.value!==undefined&&Date.now()-old.at<freshFor)return Promise.resolve(old.value as T);
 const entry:Entry=old??{at:0};entries.set(k,entry);
 const task=Promise.resolve().then(load).then(value=>{if(account===id&&entries.get(k)===entry){entry.value=value;entry.at=Date.now();}return value;}).finally(()=>{if(entry.promise===task)entry.promise=undefined;});
 entry.promise=task;return task;
}
/** Poll/SSE/mount reads join the same task; mutations explicitly invalidate then request a new one. */
export function singleFlight(run:()=>Promise<void>){let flight:Promise<void>|null=null;return()=>flight??(flight=Promise.resolve().then(run).finally(()=>{flight=null;}));}
export function keyedRefresh(run:()=>Promise<void>,getKey:()=>string){
 let active:{key:string;promise:Promise<void>}|null=null;
 const refresh=():Promise<void>=>{
  const key=getKey();if(active)return active.key===key?active.promise:active.promise.catch(()=>{}).then(refresh);
  const task=Promise.resolve().then(run).finally(()=>{if(active?.promise===task)active=null;});active={key,promise:task};return task;
 };return Object.assign(refresh,{settled:()=>active?.promise??Promise.resolve()});
}
