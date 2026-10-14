import test from 'node:test';
import assert from 'node:assert/strict';
import {phase2Fixtures} from '../demo-fixtures.ts';
import {canEdit,displayUtc,isCanonicalId,pickFields,safeRejectedError,safeWebsite,toPageViews,toProjectView,validateFields} from '../view-model.ts';

test('unknown rating, time and percent stay unknown without changing progress/membership',()=>{
  const input={...phase2Fixtures()[2],rating:null,discovered_at:null,progress_percent:null,home_membership:'removed'};
  const before=JSON.stringify(input),view=toProjectView(input,'demo');
  assert.equal(view.record.rating,null);assert.equal(view.discoveredLabel,'未知');assert.equal(view.percentLabel,'未知');
  assert.equal(view.record.progress_stage,'todo');assert.equal(view.record.home_membership,'removed');assert.equal(JSON.stringify(input),before);
});
test('ratings include D/null, percent zero is distinct from null and is not derived from stage',()=>{
  const d=toProjectView(phase2Fixtures()[7],'demo');assert.equal(d.record.rating,'D');assert.equal(d.percentLabel,'0%');
  const inconsistentButTruthful=toProjectView({...phase2Fixtures()[8],progress_percent:null},'demo');
  assert.equal(inconsistentButTruthful.progressLabel,'已完成');assert.equal(inconsistentButTruthful.percentLabel,'未知');
});
test('live projection rejects demo IDs and does not invent canonical IDs',()=>{
  const sample=phase2Fixtures()[0];assert.throws(()=>toProjectView(sample,'live'));
  const canonical='prj_550e8400-e29b-41d4-a716-446655440000';
  assert.equal(isCanonicalId(canonical),true);assert.equal(toProjectView({...sample,project_id:canonical},'live').key,canonical);
  assert.equal(isCanonicalId('Orbit Layer'),false);assert.equal(isCanonicalId('prj_PLACEHOLDER'),false);
});
test('page requires unique stable keys and never accepts more than 100 rows',()=>{
  const sample=phase2Fixtures()[0];assert.throws(()=>toPageViews([sample,sample],'demo'));
  assert.throws(()=>toPageViews(Array.from({length:101},(_,i)=>({...sample,project_id:`demo-${i}`})),'demo'));
});
test('safe projection excludes extra raw/private fields and preserves plain text',()=>{
  const sample={...phase2Fixtures()[0],raw_payload:{hunter:'PRIVATE'},hunter_accounts:['PRIVATE'],notes:'<script>plain text</script>'};
  const view=toProjectView(sample,'demo');assert.equal('raw_payload' in view.record,false);assert.equal('hunter_accounts' in view.record,false);
  assert.equal(view.record.notes,'<script>plain text</script>');
  const fields=pickFields(sample);assert.equal('project_id' in fields,false);assert.equal('discovered_at' in fields,false);assert.equal('home_membership' in fields,false);
});
test('URL and token-date validation rejects credentials/scripts/invalid dates',()=>{
  assert.equal(safeWebsite('javascript:alert(1)'),null);assert.equal(safeWebsite('https://user:secret@example.com'),null);
  assert.equal(safeWebsite(null),null);assert.equal(safeWebsite('https://project.example'),'https://project.example/');
  const base=pickFields(phase2Fixtures()[2]);
  assert.ok(validateFields({...base,token_date:'2026-02-30',token_date_status:'estimated'}));
  assert.ok(validateFields({...base,token_date:null,token_date_status:'confirmed'}));
  assert.equal(validateFields({...base,name:'x'.repeat(120),notes:'n'.repeat(4000)}),null);
});
test('UTC display converts known time to Beijing, leaves missing/malformed time unknown',()=>{
  assert.equal(displayUtc('2026-10-01T02:30:00.000Z'),'2026-10-01 10:30');
  assert.equal(displayUtc('2026-10-01T02:30:00.123456+00:00'),'2026-10-01 10:30');
  for(const value of [null,'2026-10-01','2026-02-30T00:00:00Z','private raw value'])assert.equal(displayUtc(value),'未知');
});
test('live edit capability defaults false, user stays read-only, rejected callbacks expose no raw error',()=>{
  assert.equal(canEdit({mode:'live'}),false);
  assert.equal(canEdit({mode:'live',role:'superadmin'}),false);
  assert.equal(canEdit({mode:'demo',role:'user',capabilities:{can_edit_projects:true}}),false);
  assert.equal(canEdit({mode:'live',role:'superadmin',capabilities:{can_edit_projects:true}}),true);
  const error=safeRejectedError('public-request');assert.equal(error.code,'INTERNAL_ERROR');assert.equal(error.request_id,'public-request');assert.equal(error.retryable,false);
});
