import {test} from 'node:test';
import assert from 'node:assert/strict';
import {providerHealth} from '../lib/provider-6551-health.ts';
const raw={day:'2026-10-22',used:4,limit:300,backfill_used:1,backfill_limit:300,
 recording_since:1792670000,next_probe_at:1792673600,quota_exhausted:true,realtime_paused:true,
 by_program:[{program:'tracking',calls:4}],token:'SECRET'};
test('quota plus rejected WSS shows the requested pause message without secrets',()=>{
 const result=providerHealth(raw)!;
 assert.deepEqual(result.errors,['6551 额度不足，实时推文已暂停']);
 assert.equal(JSON.stringify(result).includes('SECRET'),false);
 assert.deepEqual(result.usage.by_program,[{program:'tracking',calls:4}]);
});
test('connected WSS and paused REST remain distinct; malformed metadata is rejected',()=>{
 assert.deepEqual(providerHealth({...raw,realtime_paused:false})!.errors,['6551 额度不足，REST 已暂停']);
 assert.deepEqual(providerHealth({...raw,quota_exhausted:false})!.errors,['6551 实时连接鉴权被拒绝（HTTP 401）']);
 assert.equal(providerHealth({...raw,used:NaN}),null);
 assert.deepEqual(providerHealth({...raw,by_program:[{program:'SECRET',calls:1}]})!.usage.by_program,[]);
});
test('zero recovery budget is displayed as disabled, without a false global limit error',()=>{
 const result=providerHealth({...raw,backfill_used:0,backfill_limit:0,quota_exhausted:false,realtime_paused:false,daily_limit_reached:false})!;
 assert.equal(result.usage.backfill_limit,0);assert.deepEqual(result.errors,[]);
});
