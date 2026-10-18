import type {ProjectView} from './types';
import {validateFields} from './view-model';
import type {EditorDraft,ProjectMilestone} from './reference-types';

// Owner decision 2026-10-19: fixed project types; '' / null = 未分类.
export const PROJECT_TYPES=['NFT','发射台','新协议','撸毛','链游'] as const;
export const referenceStageLabels={todo:'待开始',researching:'研究中',watching:'持续跟踪',participating:'参与中',completed:'已完成',paused:'已暂停'} as const;
export function dateNumber(value:string|null|undefined):number|null {
  if(!value||!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const stamp=Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(stamp)&&new Date(stamp).toISOString().slice(0,10)===value?stamp:null;
}
export function dayDistance(date:string|null,asOf:string|undefined):number|null {
  const value=dateNumber(date),base=dateNumber(asOf);
  return value===null||base===null?null:Math.round((value-base)/86400000);
}
export function validHour(hour:unknown):hour is string {return typeof hour==='string'&&/^(?:[01]\d|2[0-3])$/.test(hour);}
// Calendar wall-time order, all inputs interpreted in Asia/Shanghai, independent of browser timezone.
export function milestoneNumber(event:Pick<ProjectMilestone,'date'|'hour'>):number|null {
  const date=dateNumber(event.date);return date===null?null:date+(validHour(event.hour)?Number(event.hour)*3600000:86400000-1);
}
export function milestoneLabel(event:Pick<ProjectMilestone,'date'|'hour'>,full=false):string {
  if(!event.date)return '未确认';
  return (full?event.date:event.date.slice(5).replace('-','/'))+' '+(validHour(event.hour)?event.hour+'时':'小时未确认');
}
export function matchesDiscoveryDate(project:ProjectView,date:string):boolean {
  return !date||dateNumber(date)!==null&&project.discoveredLabel!=='未知'&&project.discoveredLabel.slice(0,10)===date;
}
export function validateDraft(draft:EditorDraft):string|null {
  const fieldsError=validateFields(draft.fields);if(fieldsError)return fieldsError;
  if(draft.archive_after_save&&draft.fields.progress_stage!=='completed')return '移出完成记录前，请明确将进度设为已完成。';
  const event=draft.milestone;
  if(event.hour!==null&&!validHour(event.hour))return '请选择 00 至 23 时的有效小时。';
  if(event.date===null&&event.hour!==null)return '未知事件日期不能保存确定的小时。';
  if(event.title.length>240)return '重要事件最多 240 字符。';
  if(event.date!==null&&(dateNumber(event.date)===null||!event.title.trim()))return '请填写有效的重要时间及事件名称。';
  if(event.date===null&&event.status!=='unconfirmed')return '未知事件日期必须保持未确认。';
  if(event.date!==null&&!['confirmed','estimated'].includes(event.status))return '请注明事件时间是预计还是已确认。';
  return null;
}
export function currentMilestone(project:ProjectView,items:readonly ProjectMilestone[]):ProjectMilestone {
  const item=items.find(item=>item.project_id===project.key);
  if(item&&(!item.date||dateNumber(item.date)!==null)&&typeof item.title==='string'&&item.title.length<=240&&['confirmed','estimated','unconfirmed'].includes(item.status))return {project_id:item.project_id,date:item.date,hour:validHour(item.hour)?item.hour:null,title:item.title,status:item.status};
  // Only a real supplied token date may be shown as a token milestone fallback.
  return {project_id:project.key,date:project.record.token_date,hour:null,title:project.record.token_date?'发币日期':'',status:project.record.token_date_status};
}
export function upcomingProjects(projects:readonly ProjectView[],milestones:readonly ProjectMilestone[],asOf:string|undefined,windowDays:number|null){
  return projects.map(project=>({project,event:currentMilestone(project,milestones)})).filter(({event})=>{
    if(!event.date)return false;
    const days=dayDistance(event.date,asOf);
    return days===null?windowDays===null:days>=0&&(windowDays===null||days<=windowDays);
  }).sort((a,b)=>(milestoneNumber(a.event)!-milestoneNumber(b.event)!)||a.project.key.localeCompare(b.project.key)).slice(0,3);
}
export function shortDiscovery(label:string):string {
  // Compact (owner 2026-10-19): 10/17 14时
  return label==='未知'?'未知':label.slice(5,10).replace('-','/')+' '+label.slice(11,13)+'时';
}
