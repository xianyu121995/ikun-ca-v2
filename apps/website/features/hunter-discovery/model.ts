/** Page-private phase2-v1.0.0 projection types. No cross-worktree/shared type import. */
export type Rating = 'S' | 'A' | 'B' | 'C' | 'D' | null;
export type CommandState = 'accepted' | 'pending' | 'running' | 'succeeded' | 'failed' | 'unknown';
export type ReviewState = 'pending' | 'reviewed' | 'tracking' | 'ignored';
export type ProgressStage = 'todo' | 'researching' | 'watching' | 'participating' | 'completed' | 'paused';
export interface ProjectFields {
  name: string; rating: Rating; description: string; website_url: string | null;
  notes: string; category: string | null; progress_stage: ProgressStage;
  progress_percent: number | null; token_date: string | null;
  token_date_status: 'confirmed' | 'estimated' | 'unconfirmed';
}
export interface DiscoveryDTO {
  discovery_id: string; project_id: string | null; project: ProjectFields;
  x_user_id: string | null; x_handle: string; profile_bio: string; followers: number | null;
  signal_count: number; first_seen_at: string | null; last_seen_at: string | null;
  discovered_at: string | null; review_state: ReviewState; monitoring_state: CommandState | null;
  revision: number;
}
export interface HunterAccountDTO {
  account_id: string; x_handle: string; label: string; notes: string; enabled: boolean;
  baseline_ready: boolean; connection: 'unconfigured' | 'connecting' | 'connected' | 'disconnected';
  last_signal_at: string | null; revision: number;
}
export interface CommandResult {
  command_id: string; state: CommandState; project_id: string | null; subscription_id: string | null;
  revision: number | null; updated_at: string; error_code: string | null; request_id: string;
}
export interface ViewContext {
  mode: 'demo' | 'live'; role: 'superadmin' | 'user';
  capabilities?: Partial<{can_edit_projects: boolean; can_manage_hunter: boolean}>;
}
export interface PublicError {code: string; message: string; request_id?: string}
export type ActionResult<T> = {ok: true; data: T} | {ok: false; error: PublicError};
export interface ResearchInput {
  discovery_id: string; project_id: string | null; expected_revision: number; project: ProjectFields;
}
export interface MonitoringInput {
  discovery_id: string; expected_revision: number; confirmed: true; project: ProjectFields;
}
export interface DiscoveryCallbacks {
  onSaveResearch?: (input: ResearchInput) => Promise<ActionResult<DiscoveryDTO>>;
  onRequestMonitoring?: (input: MonitoringInput) => Promise<ActionResult<CommandResult>>;
  onCheckCommand?: (commandId: string) => Promise<ActionResult<CommandResult>>;
  onRefresh?: () => void;
  onNextPage?: (cursor: string) => void;
  onManageHunters?: () => void;
}
export interface DiscoveryView {
  key: string; canonicalId: string | null; name: string; handle: string;
  xUrl: string | null; bio: string; followersLabel: string; signalCount: number | null;
  discoveredLabel: string; discoveredEpoch: number | null; rating: Rating;
  category: string; stageLabel: string; notes: string; reviewState: ReviewState | null;
  monitoringLabel: string; commandState: CommandState | null; source: DiscoveryDTO;
}
const grades = ['S','A','B','C','D'] as const;
const stages: Record<ProgressStage,string> = {todo:'待开始',researching:'研究中',watching:'观察中',participating:'参与中',completed:'已完成',paused:'已暂停'};
const commandStates = ['accepted','pending','running','succeeded','failed','unknown'];
export function canWrite(context: ViewContext | undefined, capability: 'can_edit_projects' | 'can_manage_hunter') {
  return context?.role === 'superadmin' && context.capabilities?.[capability] === true;
}
export function safeWebsite(value: unknown): string | null {
  if(typeof value!=='string'||!value.trim())return null;
  try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}
}
export function preciseEpoch(value: unknown): number | null {
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value))return null;
  const epoch=Date.parse(value);return Number.isFinite(epoch)?epoch:null;
}
export function displayTime(value: unknown) {
  const epoch=preciseEpoch(value);return epoch===null?'时间未知':new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(epoch).replace('/','-');
}
export function monitoringLabel(state: CommandState | null, review?: ReviewState) {
  if(state==='unknown')return '结果待核实';
  if(state==='failed')return '确认失败';
  if(state==='succeeded')return '受理完成 · 待核实';
  if(state==='accepted')return '已受理 · 待核实';
  if(state==='pending'||state==='running')return '确认处理中';
  return review==='tracking'?'已确认 · 待核实':'未提交';
}
export function toDiscoveryView(dto: DiscoveryDTO): DiscoveryView {
  const text=(x:unknown)=>typeof x==='string'?x:'';
  const validCanonical=typeof dto.project_id==='string'&&/^prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(dto.project_id);
  const p=dto.project,handle=text(dto.x_handle),validHandle=/^[a-zA-Z0-9_]{1,15}$/.test(handle);
  const command=dto.monitoring_state===null?null:commandStates.includes(dto.monitoring_state)?dto.monitoring_state:'unknown';
  // Explicit whitelist: never keep raw attribution, provider data, or extra transport fields.
  const clean: DiscoveryDTO={
    discovery_id:dto.discovery_id,project_id:dto.project_id,
    project:{name:p.name,rating:p.rating,description:p.description,website_url:p.website_url,notes:p.notes,category:p.category,progress_stage:p.progress_stage,progress_percent:p.progress_percent,token_date:p.token_date,token_date_status:p.token_date_status},
    x_user_id:dto.x_user_id,x_handle:dto.x_handle,profile_bio:dto.profile_bio,followers:dto.followers,signal_count:dto.signal_count,
    first_seen_at:dto.first_seen_at,last_seen_at:dto.last_seen_at,discovered_at:dto.discovered_at,review_state:dto.review_state,monitoring_state:command,revision:dto.revision
  };
  return {
    key:dto.discovery_id,canonicalId:validCanonical?dto.project_id:null,name:text(p.name)||'名称未知',
    handle:validHandle?handle:'账号未知',xUrl:validHandle?`https://x.com/${encodeURIComponent(handle)}`:null,
    bio:text(dto.profile_bio),followersLabel:typeof dto.followers==='number'&&Number.isFinite(dto.followers)&&dto.followers>=0?dto.followers.toLocaleString('zh-CN'):'未知',
    signalCount:Number.isSafeInteger(dto.signal_count)&&dto.signal_count>=0?dto.signal_count:null,
    discoveredLabel:displayTime(dto.discovered_at),discoveredEpoch:preciseEpoch(dto.discovered_at),
    rating:grades.includes(p.rating as typeof grades[number])?p.rating:null,
    category:text(p.category)||'赛道未知',stageLabel:stages[p.progress_stage]||'进度未知',notes:text(p.notes),
    reviewState:['pending','reviewed','tracking','ignored'].includes(dto.review_state)?dto.review_state:null,
    monitoringLabel:monitoringLabel(command,dto.review_state),commandState:command,source:clean
  };
}
/** Explicitly project admin-only fields; user projections contain no account identities. */
export function accountViews(context: ViewContext | undefined, accounts: readonly HunterAccountDTO[]) {
  if(!canWrite(context,'can_manage_hunter'))return [];
  return accounts.map(a=>({account_id:a.account_id,x_handle:a.x_handle,label:a.label,notes:a.notes,enabled:a.enabled,baseline_ready:a.baseline_ready,connection:a.connection,last_signal_at:a.last_signal_at,revision:a.revision}));
}
export function validateProject(project: ProjectFields): string | null {
  if(!project.name.trim()||project.name.length>120)return '项目名称需为 1–120 个字符。';
  if(project.description.length>4000||project.notes.length>4000)return '简介及备注分别最多 4000 个字符。';
  if(project.category&&project.category.length>80)return '赛道最多 80 个字符。';
  if(project.website_url&&!safeWebsite(project.website_url))return '官网必须为不含账号密码的 http/https 地址。';
  if(project.rating!==null&&!grades.includes(project.rating))return '请选择有效评分。';
  if(!Object.hasOwn(stages,project.progress_stage))return '请选择有效项目进度。';
  if(project.progress_percent!==null&&(!Number.isFinite(project.progress_percent)||project.progress_percent<0||project.progress_percent>100))return '进度需为 0–100，未知时留空。';
  if(project.token_date){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(project.token_date)||!Number.isFinite(Date.parse(project.token_date))||new Date(project.token_date).toISOString().slice(0,10)!==project.token_date)return '请选择有效发币日期。';
    if(!['confirmed','estimated'].includes(project.token_date_status))return '有发币日期时需标明已确认或预计。';
  }else if(project.token_date_status!=='unconfirmed')return '未提供发币日期时应为未确认。';
  return null;
}
export function localDatesToUTC(start: string, end: string) {
  if(start&&end&&start>end)return {error:'开始日期不能晚于结束日期。'};
  // Shanghai has a fixed UTC+8 offset for the prototype's supported current dates.
  return {since:start?new Date(`${start}T00:00:00+08:00`).toISOString():null,until:end?new Date(`${end}T23:59:59.999+08:00`).toISOString():null,error:null};
}
