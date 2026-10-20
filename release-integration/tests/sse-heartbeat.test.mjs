import test from 'node:test';
import assert from 'node:assert/strict';
import {withSseHeartbeat} from '../../apps/website/lib/sse-heartbeat.ts';
const decode=part=>new TextDecoder().decode(part.value);
function fixture(signal=new AbortController().signal) {
  let input,canceled=0;
  const response=new Response(new ReadableStream({start(c){input=c;},cancel(){canceled++;}}),
    {headers:{'content-type':'text/event-stream','cache-control':'no-store, private','x-request-id':'fixture'}});
  const output=withSseHeartbeat(response,signal);
  return {output,reader:output.body.getReader(),input,canceled:()=>canceled};
}
test('quiet SSE flushes immediately and emits comment heartbeats every 25 seconds',async t=>{
  t.mock.timers.enable({apis:['setInterval']});const f=fixture();
  assert.equal(decode(await f.reader.read()),': connected\n\n');
  for(let n=0;n<3;n++) { const read=f.reader.read();t.mock.timers.tick(25_000);assert.equal(decode(await read),': heartbeat\n\n'); }
  await f.reader.cancel();assert.equal(f.canceled(),1);t.mock.timers.tick(100_000);
});
test('event bytes/IDs pass through unchanged and headers prohibit compression/caching/buffering',async()=>{
  const f=fixture();await f.reader.read();
  const payload=new TextEncoder().encode('id: evt_fixture\nevent: tracking.feed.activity.created.v1\ndata: {"data":{}}\n\n');
  f.input.enqueue(payload);assert.deepEqual((await f.reader.read()).value,payload);
  assert.equal(f.output.headers.get('cache-control'),'no-store, private, no-transform');
  assert.equal(f.output.headers.get('x-accel-buffering'),'no');
  assert.equal(f.output.headers.get('content-encoding'),null);assert.equal(f.output.headers.get('content-length'),null);
  assert.equal(f.output.headers.get('x-request-id'),'fixture');await f.reader.cancel();
});
test('request abort cancels upstream and stops heartbeats',async t=>{
  t.mock.timers.enable({apis:['setInterval']});const abort=new AbortController(),f=fixture(abort.signal);
  await f.reader.read();const pending=f.reader.read();abort.abort();assert.equal((await pending).done,true);
  assert.equal(f.canceled(),1);t.mock.timers.tick(100_000);assert.equal((await f.reader.read()).done,true);
});
test('upstream auth revocation/EOF ends output instead of heartbeating forever',async t=>{
  t.mock.timers.enable({apis:['setInterval']});const f=fixture();await f.reader.read();
  const pending=f.reader.read();f.input.close();assert.equal((await pending).done,true);
  t.mock.timers.tick(100_000);assert.equal((await f.reader.read()).done,true);
});
test('upstream failure reaches EventSource for retry; no timer survives it',async t=>{
  t.mock.timers.enable({apis:['setInterval']});const f=fixture();await f.reader.read();
  const pending=f.reader.read();f.input.error(Error('fixture_disconnect'));await assert.rejects(pending,/fixture_disconnect/);
  t.mock.timers.tick(100_000);
});
test('failed auth and non-SSE responses retain their exact response and body',async()=>{
  for(const response of [Response.json({error:'unauthenticated'},{status:401}),Response.json({data:[]}),new Response(null)])
    assert.equal(withSseHeartbeat(response,new AbortController().signal),response);
});
