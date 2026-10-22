export type ProviderUsage={day:string;timezone:string;used:number;limit:number;backfill_used:number;backfill_limit:number;
 recording_since:number;quota_exhausted:boolean;realtime_paused:boolean;next_probe_at:number;by_program:{program:string;calls:number}[]};
export function providerHealth(raw:unknown):{usage:ProviderUsage;errors:string[]}|null{
 if(!raw||typeof raw!=='object')return null;
 const v=raw as Record<string,unknown>;
 const numeric=['used','limit','backfill_used','backfill_limit','recording_since','next_probe_at'];
 if(numeric.some(k=>typeof v[k]!=='number'||!Number.isFinite(v[k])||(v[k] as number)<0))return null;
 if(typeof v.day!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(v.day)||!Array.isArray(v.by_program))return null;
 const by_program=v.by_program.flatMap(r=>r&&typeof r==='object'&&['tracking','hunter','hunter_ai'].includes(r.program)&&Number.isInteger(r.calls)&&r.calls>=0?[{program:r.program,calls:r.calls}]:[]);
 const usage:ProviderUsage={day:v.day,timezone:'Asia/Shanghai',used:v.used as number,limit:v.limit as number,
  backfill_used:v.backfill_used as number,backfill_limit:v.backfill_limit as number,recording_since:v.recording_since as number,
  next_probe_at:v.next_probe_at as number,quota_exhausted:v.quota_exhausted===true,realtime_paused:v.realtime_paused===true,by_program};
 const errors:string[]=[];
 if(usage.quota_exhausted)errors.push(usage.realtime_paused?'6551 额度不足，实时推文已暂停':'6551 额度不足，REST 已暂停');
 else if(usage.realtime_paused)errors.push('6551 实时连接鉴权被拒绝（HTTP 401）');
 if(v.daily_limit_reached===true)errors.push('6551 今日调用已达上限，REST 已暂停');
 return {usage,errors};
}
