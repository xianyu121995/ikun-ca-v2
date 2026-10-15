import {progressStages,ratings,type HomepageContext,type ProjectFieldsProjection,type ProjectRecordProjection,type ProjectView,type PublicError} from './types';

export const stageLabels = {todo:'待开始',researching:'研究中',watching:'观察中',participating:'参与中',completed:'已完成',paused:'已暂停'} as const;
export const membershipLabels = {hidden:'未加入主页',active:'正在做',removed:'已移除'} as const;
export function safeWebsite(value: string | null): string | null {
  if (!value?.trim()) return null;
  try {const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password?url.href:null;} catch {return null;}
}
export function isCanonicalId(value: string): boolean {
  return /^prj_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
}
export function canEdit(context: HomepageContext): boolean {
  return context.role==='superadmin' && context.capabilities?.can_edit_projects===true;
}
export function displayUtc(value: string | null): string {
  if (!value) return '未知';
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?(Z|\+00:00)$/.test(value)||!Number.isFinite(Date.parse(value))) return '未知';
  if(new Date(value).toISOString().slice(0,19)!==value.slice(0,19))return '未知';
  return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(value));
}
function validDate(value: string): boolean {
  const parsed=Date.parse(value+'T00:00:00Z');
  return /^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(parsed)&&new Date(parsed).toISOString().slice(0,10)===value;
}
// Validation checks display fields only; this is neither auth nor a domain writer.
export function validateFields(fields: ProjectFieldsProjection): string | null {
  if (!fields.name.trim()||fields.name.length>120) return '项目名称需为 1–120 字符。';
  if (fields.rating!==null&&!ratings.includes(fields.rating)) return '评分需为 S/A/B/C/D 或未评分。';
  if (fields.description.length>4000||fields.notes.length>4000) return '简介和备注各不得超过 4000 字符。';
  if (fields.category!==null&&fields.category.length>80) return '分类不得超过 80 字符。';
  if (fields.website_url!==null&&!safeWebsite(fields.website_url)) return '官网需为不含用户名或密码的 http(s) 地址。';
  if (!progressStages.includes(fields.progress_stage)) return '进度阶段无效。';
  if (fields.progress_percent!==null&&(!Number.isFinite(fields.progress_percent)||fields.progress_percent<0||fields.progress_percent>100)) return '进度需为 0–100，未知请留空。';
  if (fields.token_date===null&&fields.token_date_status!=='unconfirmed') return '无发币日期时状态需为未确认。';
  if (fields.token_date!==null&&(!validDate(fields.token_date)||!['confirmed','estimated'].includes(fields.token_date_status))) return '发币日期需有效，并注明已确认或预计。';
  return null;
}
export function pickFields(input: ProjectFieldsProjection): ProjectFieldsProjection {
  return {name:input.name,rating:input.rating,description:input.description,website_url:input.website_url,
    notes:input.notes,category:input.category,progress_stage:input.progress_stage,progress_percent:input.progress_percent,
    token_date:input.token_date,token_date_status:input.token_date_status};
}
export function toProjectView(input: ProjectRecordProjection, mode: HomepageContext['mode']): ProjectView {
  if ((mode==='live'&&!isCanonicalId(input.project_id))||!input.project_id||!Number.isInteger(input.revision)||input.revision<1||validateFields(input)||!['active','hidden','removed'].includes(input.home_membership)) throw new Error('INVALID_PROJECT_PROJECTION');
  // Explicit projection prevents unlisted/raw fields from entering the UI record.
  const record:ProjectRecordProjection={...pickFields(input),project_id:input.project_id,home_membership:input.home_membership,
    discovered_at:input.discovered_at,revision:input.revision,created_at:input.created_at,updated_at:input.updated_at};
  const dateStatus=record.token_date_status==='estimated'?'预计':'已确认';
  return {key:record.project_id,record,discoveredLabel:displayUtc(record.discovered_at),progressLabel:stageLabels[record.progress_stage],
    percentLabel:record.progress_percent===null?'未知':`${record.progress_percent}%`,
    tokenLabel:record.token_date?`${record.token_date} · ${dateStatus}`:'未确认',website:safeWebsite(record.website_url)};
}
export function toPageViews(items:readonly ProjectRecordProjection[],mode:HomepageContext['mode']):ProjectView[] {
  if(items.length>100||new Set(items.map(item=>item.project_id)).size!==items.length)throw new Error('INVALID_PAGE_PROJECTION');
  return items.map(item=>toProjectView(item,mode));
}
export function safeRejectedError(requestId:string|null):PublicError {
  // Do not display an arbitrary thrown Error message, raw response or stack.
  return {code:'INTERNAL_ERROR',message:'操作结果未确认，请核对原请求。',retryable:false,request_id:requestId};
}
