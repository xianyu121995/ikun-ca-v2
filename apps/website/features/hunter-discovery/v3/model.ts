import seed from './reference/seed.json';
import type {TableSort} from '@ikun/ui';
export type Grade = 'S'|'A'|'B'|'C'|'D'|null;
export type Status = 'pending'|'reviewed'|'joined';
export type MonitoringState = 'accepted'|'pending'|'running'|'succeeded'|'failed'|'unknown';
export interface AiDraft {name:string;website:string;description:string;notes:string;category?:string}
// Owner decision 2026-10-19: 项目类型 replaces the never-opened 代币计划 field ('' = 未分类).
export const PROJECT_TYPES=['NFT','发射台','新协议','撸毛','链游'] as const;
export interface Project {ai?:AiDraft|null;id:string;name:string;handle:string;bio:string;hunters:number;grade:Grade;status:Status;foundAt:number;website:string;description:string;category:string;notes:string;watch:boolean;monitoringMessage?:string;monitoringState?:MonitoringState|null}
export interface Filters {query:string;time:string;grade:string;status:string}
export const initialFilters:Filters={query:'',time:'all',grade:'all',status:'all'};
export const statusText:Record<Status,string>={pending:'待研究',reviewed:'已研究',joined:'已加入监控'};
export const SUBMITTING_LABEL='提交中';
export const UNVERIFIED_LABEL='结果待核实';
const succeeded=(project:Pick<Project,'status'|'monitoringState'>)=>project.monitoringState==='succeeded'||(project.status==='joined'&&project.monitoringState!=='unknown');
/** In-flight submit ids only. Settled successes must not stay in this set. */
export function beginMonitoringSubmit(inFlight:ReadonlySet<string>,id:string){const next=new Set(inFlight);next.add(id);return next;}
export function finishMonitoringSubmit(inFlight:ReadonlySet<string>,id:string){const next=new Set(inFlight);next.delete(id);return next;}
const knownMonitoring=(project:Pick<Project,'monitoringState'>)=>!!project.monitoringState&&project.monitoringState!=='unknown';
export function selectUnverifiedIds(extra:Iterable<string>,projects:Iterable<Pick<Project,'id'|'status'|'monitoringState'>>){const list=[...projects];const byId=new Map(list.map(project=>[project.id,project]));const ids=new Set<string>();for(const id of extra){const project=byId.get(id);if(project&&knownMonitoring(project))continue;ids.add(id);}for(const project of list)if(project.monitoringState==='unknown')ids.add(project.id);return ids;}
export function isTrackedDiscovery(project:Pick<Project,'status'|'monitoringState'>){if(project.monitoringState==='unknown'||project.monitoringState==='failed')return false;return succeeded(project)||project.monitoringState==='accepted'||project.monitoringState==='pending'||project.monitoringState==='running';}
/** In-flight first, then a real monitoring label. 「结果待核实」 is only a genuine unknown result. */
export function discoveryStatusLabel(project:Pick<Project,'status'|'monitoringMessage'|'monitoringState'>,flags?:{inFlight?:boolean;unverified?:boolean}){if(flags?.inFlight)return SUBMITTING_LABEL;if(project.monitoringState==='unknown'||(flags?.unverified&&!knownMonitoring(project)))return UNVERIFIED_LABEL;if(project.monitoringMessage)return project.monitoringMessage;if(succeeded(project))return '追踪中';if(project.monitoringState==='accepted')return '已受理';if(project.monitoringState==='pending'||project.monitoringState==='running')return '确认处理中';if(project.monitoringState==='failed')return '确认失败';return statusText[project.status];}
export type SubscriptionCue={project_id:string;error_code?:string;desired_state?:string;observed_state?:string;connection?:string};
/** Terminal command states from hunter win. Live subscriptions only fill in a join that is still pending. */
export function liveMonitoringPatch<T extends {review_state:string;monitoring_state:MonitoringState|null;project_id:string|null}>(item:T,subscription:SubscriptionCue|undefined):T & {monitoring_message?:string}{
  if(item.review_state!=='tracking')return item;
  if(item.monitoring_state==='succeeded'||item.monitoring_state==='failed'||item.monitoring_state==='unknown')return item;
  const monitoring_state:MonitoringState=subscription?.error_code?'failed':subscription?.desired_state==='running'&&subscription.observed_state==='running'&&subscription.connection==='connected'?'succeeded':'pending';
  const monitoring_message=subscription?.error_code?'失败：'+subscription.error_code:monitoring_state==='succeeded'?'追踪中':subscription?.desired_state==='removed'?'追踪已移除':subscription?.desired_state==='stopped'?'追踪已停止':subscription?'监听连接中':'订阅投递中或追踪服务暂不可用';
  return {...item,monitoring_state,monitoring_message};
}
export function joinActionLabel(project:Pick<Project,'status'|'monitoringMessage'|'monitoringState'>|null|undefined,flags:{live?:boolean;inFlight?:boolean;unverified?:boolean}){if(!flags.live)return project?.status==='joined'?'✓ 已加入（演示）':'＋ 加入猎手项目监控';if(!project)return flags.inFlight?SUBMITTING_LABEL:'＋ 加入猎手项目监控';if(flags.inFlight||project.monitoringState==='unknown'||(flags.unverified&&!knownMonitoring(project))||isTrackedDiscovery(project)){const label=discoveryStatusLabel(project,flags);return flags.inFlight||label.length<=8?label:(succeeded(project)?'追踪中':'确认处理中');}return '＋ 加入猎手项目监控';}
export function joinSubmissionBlocked(project:Pick<Project,'status'|'monitoringState'>|null|undefined,flags:{pending?:boolean;writable?:boolean;inFlight?:boolean;unverified?:boolean}){if(flags.pending||flags.writable===false||flags.inFlight)return true;if(!project)return false;if(project.monitoringState==='unknown'||(flags.unverified&&!knownMonitoring(project)))return true;return isTrackedDiscovery(project);}
export function createProjects(now:number):Project[]{return seed.map((r,i)=>({id:`demo-${i+1}`,name:String(r[0]),handle:String(r[1]),bio:String(r[2]),hunters:Number(r[3]),grade:r[4]==='none'?null:r[4] as Grade,status:r[5] as Status,foundAt:now-Number(r[6])*3600000,website:i%3===0?'https://example.org/':'',description:i===2?'早期 DeFi 项目，研究储备证明与模块化策略。':'',category:'',notes:'',watch:false}));}
export function filterProjects(projects:Project[],filters:Filters,sort:TableSort,now:number){const q=filters.query.trim().toLowerCase();const ranks={S:5,A:4,B:3,C:2,D:1,none:0};return projects.filter(p=>(!q||[p.name,p.handle,p.bio,p.description,p.notes].join(' ').toLowerCase().includes(q))&&(filters.time==='all'||now-p.foundAt<=Number(filters.time)*3600000)&&(filters.grade==='all'||(p.grade??'none')===filters.grade)&&(filters.status==='all'||p.status===filters.status)).sort((a,b)=>{const value=sort.key==='time'?a.foundAt-b.foundAt:sort.key==='name'?a.name.localeCompare(b.name):sort.key==='hunters'?a.hunters-b.hunters:ranks[a.grade??'none']-ranks[b.grade??'none'];return (sort.direction==='asc'?value:-value)||a.id.localeCompare(b.id,undefined,{numeric:true});});}
export function validateProject(p:Project):Record<string,string>{const errors:Record<string,string>={};if(!p.name.trim())errors.name='项目名称不能为空';if(p.name.trim().length>120)errors.name='项目名称不能超过 120 字';if(p.website.trim()){try{const u=new URL(p.website.trim());if(!['http:','https:'].includes(u.protocol)||u.username||u.password)throw new Error();}catch{errors.website='请输入有效的 http:// 或 https:// 官网地址';}}return errors;}
export function normalizeProject(p:Project):Project{return {...p,name:p.name.trim(),bio:p.bio.trim(),website:p.website.trim(),description:p.description.trim(),notes:p.notes.trim()};}
export function normalizeHandle(input:string){const handle=input.trim().replace(/^@/,'').toLowerCase();return /^[a-z0-9_]{1,15}$/.test(handle)?handle:null;}
export const formatTime=(ms:number)=>!Number.isFinite(ms)?'时间未知':new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(ms);
