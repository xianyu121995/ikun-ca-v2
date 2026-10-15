import test from 'node:test';
import assert from 'node:assert/strict';
import {referenceFixtures,DEMO_AS_OF} from '../reference-fixtures.ts';
import {currentMilestone,dateNumber,dayDistance,matchesDiscoveryDate,milestoneLabel,milestoneNumber,upcomingProjects,validateDraft} from '../reference-model.ts';
import {pickFields,toPageViews} from '../view-model.ts';
const fixtures=referenceFixtures();const views=toPageViews(fixtures.projects,'demo');
test('calendar arithmetic rejects invalid dates and uses an explicit supplied reference date',()=>{
  assert.equal(dateNumber('2026-02-30'),null);assert.equal(dateNumber('not-a-date'),null);
  assert.equal(dayDistance('2026-10-18',DEMO_AS_OF),3);assert.equal(dayDistance('2026-10-18',undefined),null);
});
test('important events are separate from token dates and never invent missing event dates',()=>{
  const nova=views.find(view=>view.record.name==='Nova Network');
  assert.equal(nova.record.token_date,null);assert.equal(currentMilestone(nova,fixtures.milestones).date,'2026-10-22');
  assert.equal(currentMilestone(nova,[]).date,null);
});
test('upcoming events sort by date, limit to three and respect future windows and grade input',()=>{
  assert.deepEqual(upcomingProjects(views,fixtures.milestones,DEMO_AS_OF,null).map(row=>row.project.record.name),['Prism Labs','Nova Network','Orbit Network']);
  assert.equal(upcomingProjects(views,fixtures.milestones,DEMO_AS_OF,7).length,2);
  assert.deepEqual(upcomingProjects(views.filter(view=>view.record.rating==='S'),fixtures.milestones,DEMO_AS_OF,7).map(row=>row.project.record.name),['Prism Labs']);
});
test('draft validation preserves field whitelist and rejects event-only or implicit completion mistakes',()=>{
  const fields=pickFields(fixtures.projects[0]);const draft={fields,milestone:{date:'2026-10-16',hour:'00',title:'主网上线',status:'estimated'},archive_after_save:false};
  assert.equal(validateDraft(draft),null);assert.equal(fields.token_date,'2026-10-18');
  assert.ok(validateDraft({...draft,milestone:{...draft.milestone,title:''}}));
  assert.ok(validateDraft({...draft,archive_after_save:true}));
  assert.equal(validateDraft({...draft,fields:{...fields,progress_stage:'completed'},archive_after_save:true}),null);
  assert.equal(Object.hasOwn(fields,'project_id'),false);assert.equal(Object.hasOwn(fields,'discovered_at'),false);
});
test('reference fixtures retain demo keys, known UTC and unknown percentages without fabricated time',()=>{
  assert.equal(views.length,12);assert.ok(views.every(view=>view.key.startsWith('demo-reference-')));
  assert.equal(views[0].discoveredLabel,'2026-10-07 13:00');assert.ok(views.every(view=>view.record.progress_percent===null));
});

test('hour sorting and display preserve midnight, 23 and unknown without timezone conversion',()=>{
  const event={date:'2026-10-18',hour:'00'};
  assert.equal(milestoneLabel(event),'10/18 00时');assert.equal(milestoneLabel({...event,hour:'23'},true),'2026-10-18 23时');
  assert.ok(milestoneNumber(event)<milestoneNumber({...event,hour:'23'}));
  assert.ok(milestoneNumber({...event,hour:'23'})<milestoneNumber({...event,hour:null}));
  assert.equal(currentMilestone(views[0],[]).hour,null);
  assert.equal(milestoneLabel({...event,hour:null}),'10/18 小时未确认');
  const draft={fields:pickFields(fixtures.projects[0]),milestone:{...event,title:'事件',status:'estimated'},archive_after_save:false};
  for(const hour of ['24','-1','0','NaN',0])assert.ok(validateDraft({...draft,milestone:{...draft.milestone,hour}}));
  for(const hour of ['00','23',null])assert.equal(validateDraft({...draft,milestone:{...draft.milestone,hour}}),null);
});
test('discovery calendar filter uses Beijing dates, combines with query input and excludes unknown dates',()=>{
  const data=[{...fixtures.projects[0],discovered_at:'2026-10-14T17:00:00Z'},{...fixtures.projects[1],discovered_at:null}];
  const [late,unknown]=toPageViews(data,'demo');
  assert.equal(matchesDiscoveryDate(late,'2026-10-15'),true);assert.equal(matchesDiscoveryDate(late,'2026-10-14'),false);
  assert.equal(matchesDiscoveryDate(unknown,'2026-10-15'),false);assert.equal(matchesDiscoveryDate(unknown,''),true);
  assert.equal(matchesDiscoveryDate(late,'2026-02-30'),false);
});
test('same-day upcoming events use hour order before stable IDs',()=>{
  const milestones=fixtures.milestones.map((event,index)=>({...event,date:'2026-10-18',hour:['23','00','09'][index]||'22'}));
  assert.deepEqual(upcomingProjects(views.slice(0,3),milestones,DEMO_AS_OF,null).map(row=>row.project.record.name),['Nova Network','Orbit Network','Prism Labs']);
});
