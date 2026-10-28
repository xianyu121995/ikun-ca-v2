import type {ProjectView} from './types';
import type {ProjectRecordProjection} from './types';
import {currentMilestone} from './reference-model';
import type {AiTimelineEntry,ProjectMilestone} from './reference-types';

export function safeTweetUrl(value:string|null|undefined):string|null {
  if(!value)return null;
  try {
    const url=new URL(value);
    if(url.protocol!=='https:'||url.hostname!=='x.com')return null;
    if(!/^\/[A-Za-z0-9_]{1,15}\/status\/[0-9]{1,40}$/.test(url.pathname))return null;
    return url.toString();
  } catch { return null; }
}

function stub(entry:AiTimelineEntry):ProjectView {
  const rating=entry.rating==='S'||entry.rating==='A'||entry.rating==='B'?entry.rating:null;
  const record:ProjectRecordProjection={
    project_id:entry.project_id,name:entry.project_name||'未命名项目',rating,description:'',website_url:null,notes:'',
    category:null,progress_stage:'watching',progress_percent:null,token_date:null,token_date_status:'unconfirmed',
    home_membership:'active',discovered_at:null,revision:1,created_at:'1970-01-01T00:00:00Z',updated_at:'1970-01-01T00:00:00Z',
  };
  return {key:entry.project_id,record,discoveredLabel:'未知',progressLabel:'持续跟踪',percentLabel:'—',tokenLabel:'未确认',website:null};
}

export function shownMilestone(project:ProjectView,milestones:readonly ProjectMilestone[],entries:readonly AiTimelineEntry[]) {
  const manual=currentMilestone(project,milestones);
  if(manual.date)return {event:manual,ai:null as AiTimelineEntry|null};
  const ai=entries.find(entry=>entry.project_id===project.key&&entry.date);
  if(!ai)return {event:manual,ai:null as AiTimelineEntry|null};
  const event:ProjectMilestone={project_id:project.key,date:ai.date,hour:ai.hour,title:ai.title,status:ai.status};
  return {event,ai};
}

export type TimelineRow={project:ProjectView;event:ProjectMilestone;ai?:AiTimelineEntry};

export function aiTimelineRows(entries:readonly AiTimelineEntry[],projects:readonly ProjectView[]):TimelineRow[] {
  return entries.filter(entry=>entry.date).map(entry=>{
    const project=projects.find(item=>item.key===entry.project_id)??stub(entry);
    const event:ProjectMilestone={project_id:entry.project_id,date:entry.date,hour:entry.hour,title:entry.title,status:entry.status};
    return {project,event,ai:{...entry,source_url:safeTweetUrl(entry.source_url)}};
  });
}
