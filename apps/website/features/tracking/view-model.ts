import type { ActionInput, ActivityDTO, AddInput, CommandDTO, PublicError, SubscriptionDTO, TrackingProps } from "./types";
const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const dayFormat = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" });
export const validProjectId = (id: string) => new RegExp(`^prj_${uuid}$`).test(id);
export const validSubscriptionId = (id: string) => new RegExp(`^sub_${uuid}$`).test(id);
export const validCommandId = (id: string) => new RegExp(`^cmd_${uuid}$`).test(id);
export const stateLabels = {
  desired: { running: "期望运行", stopped: "期望停止", removed: "期望移除" },
  observed: { running: "远端运行", stopped: "远端停止", unknown: "远端未知", absent: "远端不存在" },
  operation: { accepted: "已受理", pending: "排队中", running: "执行中", succeeded: "已确认", failed: "失败", unknown: "结果待核实" },
  connection: { unconfigured: "未配置", connecting: "连接中", connected: "来源已连接", disconnected: "来源已断开" },
} as const;
export function canWrite(props: Pick<TrackingProps, "role" | "capabilities">) {
  return props.role === "superadmin" && props.capabilities?.can_manage_tracking === true;
}
export function mutationBlock(row: SubscriptionDTO, locallyPending = false, receipt?: CommandDTO): string | null {
  if (locallyPending) return "请求提交中";
  if (row.operation_state === "unknown" || receipt?.state === "unknown") return "结果待核实，请先查询原回执";
  if (["accepted", "pending", "running"].includes(row.operation_state) || receipt && ["accepted", "pending", "running"].includes(receipt.state)) return "等待业务完成确认";
  if (row.observed_state === "unknown") return "远端状态未知，请先核实";
  if (row.desired_state === "removed") return "监控已移除";
  return null;
}
export function isUnverified(row: SubscriptionDTO, mark?: { revision: number; queried: boolean }): boolean {
  return !!mark && (!mark.queried || row.revision <= mark.revision || row.operation_state === "unknown" || row.observed_state === "unknown");
}
export function toAction(row: SubscriptionDTO, operation: ActionInput["operation"]): ActionInput {
  if (!validSubscriptionId(row.subscription_id) || !validProjectId(row.project_id)) throw new Error("订阅或项目标识无效");
  return { subscription_id: row.subscription_id, project_id: row.project_id, revision: row.revision, operation };
}
export const primaryOperation = (row: SubscriptionDTO): ActionInput["operation"] => row.observed_state === "running" ? "stop" : row.observed_state === "absent" ? "start" : "resume";
export const operationLabel = (operation: ActionInput["operation"]) => ({ start: "启动", stop: "停止", resume: "恢复", remove: "移除" })[operation];
export function validateAdd(input: AddInput): string | null {
  if (!validProjectId(input.project_id)) return "请先选择已注册的 canonical 项目";
  if (!input.name.trim() || input.name.trim().length > 120) return "项目名称应为 1–120 字符";
  if (!/^[A-Za-z0-9_]{1,15}$/.test(input.x_handle)) return "X 账号应为不含 @ 的 1–15 位字母、数字或下划线";
  if (input.notes.length > 4000) return "备注最多 4000 字符";
  if (input.confirmed !== true) return "请明确确认加入监控";
  return null;
}
export function validateReceipt(command: CommandDTO, row?: SubscriptionDTO): boolean {
  return validCommandId(command.command_id) && (!row || command.subscription_id === row.subscription_id && command.project_id === row.project_id) &&
    (command.subscription_id === null || validSubscriptionId(command.subscription_id)) &&
    (command.project_id === null || validProjectId(command.project_id)) &&
    Object.hasOwn(stateLabels.operation, command.state);
}
export function projectRows(rows: SubscriptionDTO[], query: string, status: string, sort: string, includeRemoved = false) {
  const q = query.trim().toLowerCase();
  return rows.filter(r => (includeRemoved || r.desired_state !== "removed") &&
    `${r.name} ${r.x_handle} ${r.subscription_id} ${r.project_id}`.toLowerCase().includes(q) &&
    (status === "all" || status === "unknown" && (r.operation_state === "unknown" || r.observed_state === "unknown") ||
      status === "pending" && ["accepted", "pending", "running"].includes(r.operation_state) || status === "failed" && r.operation_state === "failed" ||
      status === "running" && r.observed_state === "running" && r.operation_state === "succeeded" || status === "stopped" && r.observed_state === "stopped"))
    .sort((a, b) => sort === "name" ? a.name.localeCompare(b.name) : sort === "updated" ? Date.parse(b.updated_at) - Date.parse(a.updated_at) : (Date.parse(b.last_tweet_at || "") || 0) - (Date.parse(a.last_tweet_at || "") || 0));
}
export function activityTime(activity: ActivityDTO) {
  return { at: activity.occurred_at ?? activity.received_at, receivedOnly: activity.occurred_at === null };
}
/** Only the supplied subscription/project pairs belong in this page's tweet feed. */
export function trackingActivities(activities: ActivityDTO[], subscriptions: SubscriptionDTO[], project = "all", query = "", sort = "latest", day = "") {
  const subscriptionsById = new Map(subscriptions.map(row => [row.subscription_id, row.project_id]));
  const q = query.trim().toLowerCase();
  return activities.filter(activity => subscriptionsById.get(activity.subscription_id) === activity.project_id &&
    (project === "all" || activity.project_id === project) &&
    `${activity.project_name} ${activity.x_handle} ${activity.text}`.toLowerCase().includes(q) &&
    (!day || Number.isFinite(Date.parse(activityTime(activity).at)) && dayFormat.format(new Date(activityTime(activity).at)) === day))
    .sort((a, b) => ((Date.parse(activityTime(b).at) || 0) - (Date.parse(activityTime(a).at) || 0)) * (sort === "oldest" ? -1 : 1));
}
export function safeTweetURL(raw: string): string | null {
  try {
    const url = new URL(raw);
    return url.protocol === "https:" && ["x.com", "www.x.com"].includes(url.hostname) && !url.username && !url.password && !url.port && /^\/[A-Za-z0-9_]{1,15}\/status\/\d+$/.test(url.pathname) ? url.href : null;
  } catch { return null; }
}
export function publicError(error: unknown): PublicError {
  const value = error as Partial<PublicError> | null;
  // Only explicit public error fields are rendered. Raw Error.message/stack stays out of UI.
  return value && typeof value.code === "string" && typeof value.message === "string" && typeof value.request_id === "string" ?
    { code: value.code, message: value.message, request_id: value.request_id, retryable: value.retryable === true } :
    { code: "INTERNAL_ERROR", message: "未取得可核实结果，请查询原回执。", request_id: "未提供", retryable: false };
}
export const formatTime = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)) : "未知";
