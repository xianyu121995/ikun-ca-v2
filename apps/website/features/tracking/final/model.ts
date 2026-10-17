/** Page presentation only. ui_key is a local rendering key, never a canonical business ID. */
export type Grade = "S" | "A" | "B";
export interface Account {
  ui_key: string; name: string; handle: string; note: string; grade: Grade | "C" | "D" | null;
  status: "running" | "starting" | "stopping" | "failed" | "unknown" | "stopped";
  avatar: string;
}
export interface Media {
  kind: "demo" | "image" | "video";
  title: string; caption: string; theme?: string; src?: string;
}
export interface Post {
  ui_key: string; account_key: string; published_at: string | null;
  quoted_tweet?: {tweet_id:string;text:string;author_handle:string;author_name:string;url:string}|null;
  tweet_kind?:string;
  translation_zh?:{text:string;quote:string|null}|null;
  body: string; important: boolean | null; original_url?:string; media_available?:boolean; received_at?:string; comments: string; reposts: string; likes: string;
  media: Media | null;
}
export interface AccountInput { handle: string; name: string; note: string; grade: Grade }
export interface Filters { query: string; grade: Grade | "all"; hours: "all" | "24" | "168"; important: boolean }
export const emptyFilters: Filters = { query: "", grade: "all", hours: "all", important: false };
export const PAGE_SIZE = 6;
const beijingDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" });
const beijingTime = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
export const timeOf = (post: Post) => post.published_at ? Date.parse(post.published_at) : NaN;
export const displayTime = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? beijingTime.format(new Date(value)) : "发布时间未知";
export function relativeTime(value: string | null, now: number) {
  const at = value ? Date.parse(value) : NaN;
  if (!Number.isFinite(at)) return "发布时间未知";
  if (at > now) return "时间待核实";
  const minutes = Math.max(1, Math.floor((now - at) / 60000));
  return minutes < 60 ? `${minutes} 分钟前` : minutes < 1440 ? `${Math.floor(minutes / 60)} 小时前` : `${Math.floor(minutes / 1440)} 天前`;
}
export function selectPosts(accounts: Account[], posts: Post[], filters: Filters, now: number, order: "occurred" | "received" = "occurred") {
  const map = new Map(accounts.filter(account => ["S", "A", "B"].includes(account.grade ?? "")).map(account => [account.ui_key, account]));
  const query = filters.query.trim().toLowerCase();
  return posts.filter(post => {
    const account = map.get(post.account_key); if (!account) return false;
    return (filters.grade === "all" || account.grade === filters.grade) &&
      (filters.hours === "all" || Number.isFinite(timeOf(post)) && timeOf(post) >= now - Number(filters.hours) * 3600000 && timeOf(post) <= now) &&
      (!filters.important || post.important) &&
      `${account.note} ${account.name} ${account.handle} @${account.handle} ${post.body}`.toLowerCase().includes(query);
  }).sort((a, b) => order === "received" ? 0 : (Number.isFinite(timeOf(b)) ? timeOf(b) : -Infinity) - (Number.isFinite(timeOf(a)) ? timeOf(a) : -Infinity));
}
export function paginate<T>(items: T[], requestedPage: number) {
  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const page = Math.max(1, Math.min(Math.trunc(requestedPage) || 1, totalPages));
  return { page, totalPages, items: items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), start: items.length ? (page - 1) * PAGE_SIZE + 1 : 0, end: Math.min(page * PAGE_SIZE, items.length) };
}
export function statsFor(accounts: Account[], posts: Post[], now: number) {
  const keys = new Set(accounts.map(account => account.ui_key));
  return { today: posts.filter(post => keys.has(post.account_key) && Number.isFinite(timeOf(post)) && timeOf(post) <= now && beijingDay.format(new Date(timeOf(post))) === beijingDay.format(new Date(now))).length,
    S: accounts.filter(account => account.grade === "S").length, A: accounts.filter(account => account.grade === "A").length, B: accounts.filter(account => account.grade === "B").length, total: accounts.length };
}
export function validateAccount(input: AccountInput, accounts: Account[]): string | null {
  const handle = input.handle.trim().replace(/^@/, "");
  if (!/^[A-Za-z0-9_]{1,15}$/.test(handle)) return "X 用户名应为 1–15 位英文字母、数字或下划线";
  if (!input.name.trim() || input.name.trim().length > 50) return "项目名称应为 1–50 字符";
  if (!input.note.trim() || input.note.trim().length > 80) return "请填写 1–80 字符的账号备注";
  if (!["S", "A", "B"].includes(input.grade)) return "请选择 S / A / B 级评分";
  if (accounts.some(account => account.handle.toLowerCase() === handle.toLowerCase())) return "该 X 用户名已在演示监控列表中";
  return null;
}
/** Media UI accepts local site assets only; no arbitrary remote tracking URLs or scripts. */
export const localMedia = (src?: string) => src?.startsWith("/") && !src.startsWith("//") && !/[\\\u0000-\u001f]/.test(src) ? src : null;
