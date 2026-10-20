export type ExistingTracking = {project_id:string;x_handle:string;desired_state:string;subscription_id:string};
export type ProjectTrackingResult = {status:'ready'|'already'|'added';message:string;project_revision:number;x_handle?:string|null;warning?:string};
export function normalizeXHandle(value:unknown):string|null {
  if(typeof value!=='string')return null;
  const handle=value.trim().replace(/^@/,'');return /^[A-Za-z0-9_]{1,15}$/.test(handle)?handle.toLowerCase():null;
}
export function existingTracking(rows:readonly ExistingTracking[],projectId:string,handle:string|null) {
  const active=rows.filter(row=>row.desired_state!=='removed');
  return active.find(row=>row.project_id===projectId)??active.find(row=>handle&&normalizeXHandle(row.x_handle)===handle);
}
export function existingTrackingMessage(row:ExistingTracking) {
  return row.desired_state==='stopped'?'已在追踪列表（已停止，可到追踪页恢复）':'已在追踪列表';
}
