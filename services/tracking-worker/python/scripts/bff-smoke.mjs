import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { trackingProxy } from '../integration/next/tracking-proxy.ts';

let seen;
const server=createServer(async(request,response)=>{
  let body='';for await(const chunk of request)body+=chunk;
  seen={url:request.url,headers:request.headers,body};
  response.writeHead(202,{'content-type':'application/json','etag':'"rev-2"','set-cookie':'not-forwarded=1'});
  response.end(JSON.stringify({data:{status:'pending'}}));
});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
process.env.TRACKING_API_URL=`http://127.0.0.1:${server.address().port}`;
try {
  let response=await trackingProxy(new Request('https://ikun.ca/api/v1/tracking/subscriptions/p1/stop',{
    method:'POST',headers:{cookie:'__Host-ikun_session=test-session','x-csrf-token':'csrf',
      origin:'https://ikun.ca','idempotency-key':'test-id','if-match':'"rev-1"','x-role':'superadmin',
      authorization:'Bearer must-not-forward'},body:'{}'
  }));
  assert.equal(response.status,202);
  assert.equal(response.headers.get('etag'),'"rev-2"');
  assert.equal(response.headers.get('set-cookie'),null);
  assert.equal(seen.headers.cookie,'__Host-ikun_session=test-session');
  assert.equal(seen.headers['x-csrf-token'],'csrf');
  assert.equal(seen.headers['x-role'],undefined);
  assert.equal(seen.headers.authorization,undefined);
  assert.equal(seen.url,'/api/v1/tracking/subscriptions/p1/stop');
  response=await trackingProxy(new Request('https://ikun.ca/admin'));
  assert.equal(response.status,404);
  process.env.TRACKING_API_URL='https://other-host.example';
  response=await trackingProxy(new Request('https://ikun.ca/tracking'));
  assert.equal(response.status,503);
  process.stdout.write('BFF smoke passed: cookie/CSRF/If-Match forwarding, no role/bearer injection, loopback and route allowlist.\n');
} finally {server.closeAllConnections();await new Promise(done=>server.close(done));}
