import assert from 'node:assert/strict';
import { LiveMonitorAdapter } from '../integration/monitor-adapter.mjs';
const row={project_id:'prj_550e8400-e29b-41d4-a716-446655440000',name:'项目',handle:'project',revision:1,
  created_at:'2026-10-15T00:00:00Z',updated_at:'2026-10-15T00:00:00Z',desired:'running',status:'pending',remote_state:'unknown'};
let sent;
const adapter=new LiveMonitorAdapter({fetchImpl:async(path,options)=>{
  if(path==='/api/tracking/me')return Response.json({csrf_token:'csrf',role:'superadmin'});
  if(path.endsWith('/latest?limit=100'))return Response.json({data:{items:[]}});
  if(path.includes('/subscriptions?'))return Response.json({data:{items:[row],next_cursor:null}});
  sent=options;return Response.json({data:{...row,desired:'stopped',status:'pending',revision:2}});
}});
assert.equal((await adapter.list()).projects[0].status,'starting');
assert.equal(adapter.monitor({...row,status:'recovering'}).status,'starting');
assert.equal(adapter.monitor({...row,status:'monitoring',remote_state:'active'}).status,'running');
assert.equal(adapter.monitor({...row,desired:'stopped'}).status,'stopping');
assert.equal((await adapter.stop(row.project_id)).status,'stopping');
assert.equal(sent.headers['If-Match'],'"rev-1"');
assert.equal(sent.headers['X-CSRF-Token'],'csrf');
await assert.rejects(adapter.add({name:'n',handle:'p'}),{code:'CONFIRMATION_REQUIRED'});
await assert.rejects(adapter.markRead([]),{code:'UNSUPPORTED'});
adapter.destroy();
process.stdout.write('Live UI adapter smoke passed: remote acknowledgment states, CSRF/revision, explicit confirmation, unsupported controls.\n');
