import {test} from 'node:test';
import assert from 'node:assert/strict';
import {accountViews,canWrite,displayTime,localDatesToUTC,monitoringLabel,preciseEpoch,safeWebsite,toDiscoveryView,validateProject,type DiscoveryDTO,type ViewContext} from './model';
import {demoAccounts,demoDiscoveries} from './fixtures';

test('缺少上下文或能力默认只读，user 不能通过伪造能力开启写入',()=>{
  assert.equal(canWrite(undefined,'can_edit_projects'),false);
  assert.equal(canWrite({mode:'live',role:'superadmin'},'can_edit_projects'),false);
  assert.equal(canWrite({mode:'live',role:'user',capabilities:{can_manage_hunter:true}},'can_manage_hunter'),false);
  assert.equal(canWrite({mode:'live',role:'superadmin',capabilities:{can_edit_projects:true}},'can_edit_projects'),true);
});
test('user 和无会话的账号投影为空，管理员仅得到白名单字段',()=>{
  assert.deepEqual(accountViews({mode:'demo',role:'user',capabilities:{can_manage_hunter:true}},demoAccounts),[]);
  assert.deepEqual(accountViews(undefined,demoAccounts),[]);
  const raw=Object.assign({},demoAccounts[0],{cookie:'SECRET_SENTINEL',provider_url:'SECRET_SENTINEL'});
  const view=accountViews({mode:'demo',role:'superadmin',capabilities:{can_manage_hunter:true}},[raw]);
  assert.equal(JSON.stringify(view).includes('SECRET_SENTINEL'),false);
});
test('discovery_id 与 null/canonical project_id 不互换、不生成 ID',()=>{
  const [unregistered,registered]=demoDiscoveries();
  assert.equal(toDiscoveryView(unregistered).key,unregistered.discovery_id);
  assert.equal(toDiscoveryView(unregistered).canonicalId,null);
  assert.equal(toDiscoveryView(unregistered).source.project_id,null);
  assert.equal(toDiscoveryView(registered).canonicalId,registered.project_id);
  assert.notEqual(toDiscoveryView(registered).key,registered.project_id);
});
test('展示投影不透传 Hunter 归因、raw payload 或私有扩展字段',()=>{
  const dto=demoDiscoveries()[0];
  const raw=Object.assign({},dto,{hunters:['SECRET_SENTINEL'],raw_payload:{token:'SECRET_SENTINEL'},project:{...dto.project,raw:'SECRET_SENTINEL'}});
  assert.equal(JSON.stringify(toDiscoveryView(raw)).includes('SECRET_SENTINEL'),false);
});
test('未知粉丝、评分、发生时间不会填零或伪造精确时间',()=>{
  const view=toDiscoveryView(demoDiscoveries()[0]);
  assert.equal(view.followersLabel,'未知');assert.equal(view.rating,null);assert.equal(view.discoveredLabel,'时间未知');assert.equal(view.discoveredEpoch,null);
  assert.equal(preciseEpoch('2026-10-15'),null);assert.equal(displayTime('bad'),'时间未知');
});
test('全部 CommandState 都不推导远端监控运行，tracking 仅表示已确认',()=>{
  for(const state of ['accepted','pending','running','succeeded','failed','unknown',null] as const){assert.equal(monitoringLabel(state).includes('监控运行'),false);}
  assert.match(monitoringLabel('succeeded'),/待核实/);assert.match(monitoringLabel('accepted'),/已受理/);
  assert.match(monitoringLabel('unknown'),/待核实/);assert.match(monitoringLabel(null,'tracking'),/待核实/);
});
test('安全链接不接受协议注入或 URL 用户名/密码',()=>{
  for(const url of ['javascript:alert(1)','data:text/html,test','https://user:pass@example.com','ftp://example.com'])assert.equal(safeWebsite(url),null);
  assert.equal(safeWebsite('https://example.com'),'https://example.com/');
  const dto={...demoDiscoveries()[0],x_handle:'invalid/handle'};assert.equal(toDiscoveryView(dto).xUrl,null);
});
test('评分 D 与未知进度百分比按冻结字段保留',()=>{
  const dto=demoDiscoveries()[2];assert.equal(toDiscoveryView(dto).rating,'D');assert.equal(dto.project.progress_percent,null);
  assert.equal(validateProject(dto.project),null);
  assert.match(validateProject({...dto.project,progress_percent:101})!,/0–100/);
});
test('发币日期独立于 UTC 发生时间，未知日期只能 unconfirmed',()=>{
  const fields=demoDiscoveries()[0].project;
  assert.equal(validateProject({...fields,token_date:'2026-10-15',token_date_status:'estimated'}),null);
  assert.match(validateProject({...fields,token_date:'2026-02-30',token_date_status:'confirmed'})!,/有效/);
  assert.match(validateProject({...fields,token_date:null,token_date_status:'confirmed'})!,/未确认/);
});
test('北京时间日期首尾转换为 UTC，不生成监控 checkpoint',()=>{
  assert.deepEqual(localDatesToUTC('2026-10-15','2026-10-15'),{since:'2026-10-14T16:00:00.000Z',until:'2026-10-15T15:59:59.999Z',error:null});
  assert.match(localDatesToUTC('2026-10-16','2026-10-15').error!,/不能晚于/);
});
test('异常平台时间、评分和数量保持未知，未用来源条数推断评分',()=>{
  const dto=demoDiscoveries()[0];const raw={...dto,discovered_at:'2026-10-15',followers:NaN,signal_count:NaN,project:{...dto.project,rating:'unexpected'}} as unknown as DiscoveryDTO;
  const view=toDiscoveryView(raw);assert.equal(view.discoveredEpoch,null);assert.equal(view.followersLabel,'未知');assert.equal(view.rating,null);assert.equal(view.signalCount,null);
});
